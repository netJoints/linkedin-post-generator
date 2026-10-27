"""Read an optional PDF, Word, or text attachment into plain text.

The bytes stay in memory. Nothing is written to disk, and nothing in the
file is executed. Only the extracted text is handed to the draft prompt.
"""

from __future__ import annotations

import base64
import io
import re
import zipfile
import zlib
from xml.etree import ElementTree

MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
ATTACHMENT_TEXT_LIMIT = 8_000
_MAX_UNCOMPRESSED = 12 * 1024 * 1024
_MAX_ZIP_ENTRIES = 200
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def extract_document(filename: str, data: bytes) -> dict[str, str]:
    """Return title, kind, text, and an optional shortening note."""
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError("That file is larger than 8 MB.")
    if not data:
        raise ValueError("That file is empty.")
    name = display_name(filename)
    extension = file_extension(filename)
    if extension not in _ALLOWED_EXTENSIONS:
        raise ValueError("Attach a PDF, Word document (.doc or .docx), or .txt file.")
    kind = _kind_for(extension, data)
    if kind == "pdf":
        text = _extract_pdf(data)
    elif kind == "docx":
        text = _extract_docx(data)
    elif kind == "doc":
        text = _extract_doc(data)
    else:
        text = _extract_txt(data)
    text = _normalize(text)
    if not text or (kind == "pdf" and _readability(text) < 0.45):
        raise ValueError(_empty_message(kind))
    note = ""
    if len(text) > ATTACHMENT_TEXT_LIMIT:
        shortened = text[:ATTACHMENT_TEXT_LIMIT].rsplit(" ", 1)[0].strip()
        text = shortened or text[:ATTACHMENT_TEXT_LIMIT].strip()
        note = "text was shortened to fit the draft"
    return {"title": name, "kind": "file", "text": text, "note": note, "url": ""}


def display_name(filename: str) -> str:
    base = filename.replace("\\", "/").split("/")[-1].strip()
    base = re.sub(r"[\r\n\t]+", " ", base)
    base = re.sub(r"[^\w.\- ()]", "_", base, flags=re.UNICODE).strip(" .")
    return (base or "attachment")[:180]


def file_extension(filename: str) -> str:
    base = filename.replace("\\", "/").split("/")[-1].strip()
    if "." not in base:
        return ""
    return "." + base.rsplit(".", 1)[-1].casefold()


def _kind_for(extension: str, data: bytes) -> str:
    sniffed = _sniff(data)
    if extension == ".pdf":
        if sniffed != "pdf":
            raise ValueError("That file is not a PDF.")
        return "pdf"
    if extension == ".txt":
        if sniffed != "text":
            raise ValueError("That file's contents do not match a text file.")
        return "txt"
    if extension == ".docx":
        if sniffed == "docx":
            return "docx"
        if sniffed == "doc":
            return "doc"
        raise ValueError("That file is not a Word document.")
    if sniffed == "doc":
        return "doc"
    if sniffed == "docx":
        return "docx"
    raise ValueError("That file is not a Word document.")


def _sniff(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(_OLE_MAGIC):
        return "doc"
    if data.startswith(b"PK\x03\x04") and _zip_has_word_document(data):
        return "docx"
    if data.startswith(b"PK\x03\x04"):
        return "zip"
    return "text"


def _empty_message(kind: str) -> str:
    if kind == "pdf":
        return "No readable text in that PDF. A scan without a text layer cannot be used."
    if kind in {"doc", "docx"}:
        return "No readable text in that Word document."
    return "No readable text in that file."


def _normalize(value: str) -> str:
    value = value.replace("\x00", "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[^\S\n]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _extract_txt(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    sample = data[:8192]
    if b"\x00" in sample:
        raise ValueError("That text file looks like a binary file.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _zip_has_word_document(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def _extract_docx(data: bytes) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("That file is not a Word document.") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ZIP_ENTRIES:
            raise ValueError("That document has too many internal files.")
        uncompressed = sum(info.file_size for info in infos)
        if uncompressed > _MAX_UNCOMPRESSED:
            raise ValueError("That document is too large to read.")
        names = [
            info.filename
            for info in infos
            if info.filename == "word/document.xml"
            or re.fullmatch(r"word/(header|footer)\d+\.xml", info.filename)
        ]
        if "word/document.xml" not in names:
            raise ValueError("That file is not a Word document.")
        names.sort(key=lambda name: (name != "word/document.xml", name))
        parts: list[str] = []
        for name in names:
            info = archive.getinfo(name)
            if info.file_size > _MAX_UNCOMPRESSED:
                raise ValueError("That document is too large to read.")
            xml_bytes = archive.read(name)
            parts.append(_docx_xml_to_text(xml_bytes))
    return "\n\n".join(part for part in parts if part.strip())


def _docx_xml_to_text(xml_bytes: bytes) -> str:
    if b"<!DOCTYPE" in xml_bytes or b"<!ENTITY" in xml_bytes:
        raise ValueError("That document contains unsupported markup.")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise ValueError("Could not read that Word document.") from exc
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{{{_W_NS}}}p"):
        line = _paragraph_text(paragraph).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs)


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []

    def walk(node: ElementTree.Element) -> None:
        for child in list(node):
            if child.tag == _FALLBACK:
                continue
            local = child.tag.rsplit("}", 1)[-1]
            if local == "t" and child.text:
                parts.append(child.text)
            elif local == "tab":
                parts.append("\t")
            elif local in {"br", "cr"}:
                parts.append("\n")
            else:
                walk(child)

    walk(paragraph)
    return "".join(parts)


def _extract_doc(data: bytes) -> str:
    if not data.startswith(_OLE_MAGIC):
        raise ValueError("That file is not a Word document.")
    try:
        streams = _ole_streams(data)
        word = streams.get("WordDocument")
        if not word or len(word) < 0x20:
            raise ValueError("No readable text in that Word document.")
        flags = int.from_bytes(word[0x0A:0x0C], "little")
        table_name = "1Table" if flags & 0x0200 else "0Table"
        table = streams.get(table_name) or streams.get("1Table") or streams.get("0Table")
        if table:
            text = _word_piece_text(word, table)
            if len(_normalize(text)) >= 20:
                return text
    except ValueError:
        raise
    except (IndexError, UnicodeError, OverflowError, OSError):
        pass
    return _utf16_runs(data)


def _word_piece_text(word: bytes, table: bytes) -> str:
    fc_clx, lcb_clx = _clx_location(word)
    if lcb_clx <= 0 or fc_clx < 0 or fc_clx + lcb_clx > len(table):
        fc_clx = int.from_bytes(word[0x01A2:0x01A6], "little")
        lcb_clx = int.from_bytes(word[0x01A6:0x01AA], "little")
    if lcb_clx <= 0 or fc_clx < 0 or fc_clx + lcb_clx > len(table):
        raise ValueError("No readable text in that Word document.")
    clx = table[fc_clx : fc_clx + lcb_clx]
    index = 0
    while index < len(clx) and clx[index] == 0x01:
        if index + 3 > len(clx):
            break
        size = int.from_bytes(clx[index + 1 : index + 3], "little")
        index += 3 + size
    if index >= len(clx) or clx[index] != 0x02:
        raise ValueError("No readable text in that Word document.")
    index += 1
    plc_size = int.from_bytes(clx[index : index + 4], "little")
    index += 4
    plc = clx[index : index + plc_size]
    if plc_size < 16 or (plc_size - 4) % 12 != 0:
        raise ValueError("No readable text in that Word document.")
    count = (plc_size - 4) // 12
    characters = [int.from_bytes(plc[item * 4 : item * 4 + 4], "little") for item in range(count + 1)]
    pieces = plc[(count + 1) * 4 :]
    chunks: list[str] = []
    for item in range(count):
        start_cp = characters[item]
        end_cp = characters[item + 1]
        if end_cp < start_cp:
            continue
        pcd = pieces[item * 8 : item * 8 + 8]
        if len(pcd) < 8:
            continue
        chunks.append(_pcd_text(word, pcd, end_cp - start_cp))
    return _clean_word_controls("".join(chunks))


def _clx_location(word: bytes) -> tuple[int, int]:
    if len(word) < 0x20 + 2:
        return 0, 0
    csw = int.from_bytes(word[0x20:0x22], "little")
    position = 0x22 + csw * 2
    if position + 2 > len(word):
        return 0, 0
    cslw = int.from_bytes(word[position : position + 2], "little")
    position += 2 + cslw * 4
    position += 2
    fc_at = position + 32 * 8
    if fc_at + 8 > len(word):
        return 0, 0
    fc_clx = int.from_bytes(word[fc_at : fc_at + 4], "little")
    lcb_clx = int.from_bytes(word[fc_at + 4 : fc_at + 8], "little")
    return fc_clx, lcb_clx


def _pcd_text(word: bytes, pcd: bytes, count: int) -> str:
    if count <= 0 or count > 2_000_000:
        return ""
    raw = int.from_bytes(pcd[2:6], "little")
    compressed = bool(raw & 0x40000000)
    fc = raw & 0x3FFFFFFF
    if compressed:
        offset = fc // 2
        blob = word[offset : offset + count]
        return blob.decode("cp1252", errors="replace")
    offset = fc
    blob = word[offset : offset + count * 2]
    return blob.decode("utf-16-le", errors="replace")


def _clean_word_controls(text: str) -> str:
    parts: list[str] = []
    dropping = False
    for char in text:
        if char == "\x13":
            dropping = True
            continue
        if char == "\x14":
            dropping = False
            continue
        if char == "\x15":
            dropping = False
            continue
        if dropping:
            continue
        if char in "\r\x0b\x0c":
            parts.append("\n")
        elif char == "\x07":
            parts.append("\t")
        elif char == "\t" or char == "\n" or char >= " ":
            parts.append(char)
    return "".join(parts)


def _utf16_runs(data: bytes) -> str:
    decoded = data.decode("utf-16-le", errors="ignore")
    runs = re.findall(r"[A-Za-z0-9][A-Za-z0-9 ,.;:'\"()/\-]{40,}", decoded)
    return "\n".join(runs)


def _ole_streams(data: bytes) -> dict[str, bytes]:
    if len(data) < 512 or not data.startswith(_OLE_MAGIC):
        raise ValueError("That file is not a Word document.")
    sector_size = 1 << int.from_bytes(data[0x1E:0x20], "little")
    mini_size = 1 << int.from_bytes(data[0x20:0x22], "little")
    major = int.from_bytes(data[0x1A:0x1C], "little")
    fat_count = int.from_bytes(data[0x2C:0x30], "little")
    dir_start = int.from_bytes(data[0x30:0x34], "little")
    mini_cutoff = int.from_bytes(data[0x38:0x3C], "little")
    mini_fat_start = int.from_bytes(data[0x3C:0x40], "little")
    difat_start = int.from_bytes(data[0x44:0x48], "little")
    difat_count = int.from_bytes(data[0x48:0x4C], "little")
    if sector_size not in {512, 4096} or mini_size not in {64, 128, 512}:
        raise ValueError("That file is not a Word document.")

    def sector_offset(sector_id: int) -> int:
        return 512 + sector_id * sector_size

    fat_sectors: list[int] = []
    for index in range(109):
        sector_id = int.from_bytes(data[0x4C + index * 4 : 0x50 + index * 4], "little")
        if sector_id >= 0xFFFFFFF0:
            break
        fat_sectors.append(sector_id)
    next_difat = difat_start
    seen_difat = 0
    while next_difat < 0xFFFFFFF0 and seen_difat < difat_count + 1:
        offset = sector_offset(next_difat)
        entries = sector_size // 4
        for index in range(entries - 1):
            sector_id = int.from_bytes(data[offset + index * 4 : offset + index * 4 + 4], "little")
            if sector_id >= 0xFFFFFFF0:
                break
            fat_sectors.append(sector_id)
        next_difat = int.from_bytes(data[offset + (entries - 1) * 4 : offset + entries * 4], "little")
        seen_difat += 1

    fat: list[int] = []
    for sector_id in fat_sectors[:fat_count]:
        if sector_id >= 0xFFFFFFF0:
            continue
        offset = sector_offset(sector_id)
        for index in range(0, sector_size, 4):
            fat.append(int.from_bytes(data[offset + index : offset + index + 4], "little"))

    def read_chain(start: int, size: int) -> bytes:
        if start >= 0xFFFFFFF0 or size <= 0:
            return b""
        size = min(size, _MAX_UNCOMPRESSED)
        out = bytearray()
        sector_id = start
        seen: set[int] = set()
        while sector_id < 0xFFFFFFF0 and sector_id not in seen and len(out) < size:
            seen.add(sector_id)
            offset = sector_offset(sector_id)
            if offset < 0 or offset >= len(data):
                break
            out.extend(data[offset : offset + sector_size])
            sector_id = fat[sector_id] if sector_id < len(fat) else 0xFFFFFFFE
        return bytes(out[:size])

    directory = read_chain(dir_start, _MAX_UNCOMPRESSED)
    entries: list[tuple[str, int, int, int]] = []
    for offset in range(0, len(directory), 128):
        entry = directory[offset : offset + 128]
        if len(entry) < 128:
            break
        name_len = int.from_bytes(entry[64:66], "little")
        name = ""
        if 2 <= name_len <= 64:
            name = entry[: name_len - 2].decode("utf-16-le", errors="replace").rstrip("\x00")
        obj_type = entry[66]
        start = int.from_bytes(entry[116:120], "little")
        if major >= 4:
            size = int.from_bytes(entry[120:128], "little")
        else:
            size = int.from_bytes(entry[120:124], "little")
        entries.append((name, obj_type, start, size))

    root = next((entry for entry in entries if entry[1] == 5), None)
    mini_stream = read_chain(root[2], root[3]) if root else b""
    mini_fat_blob = b""
    sector_id = mini_fat_start
    seen_mini: set[int] = set()
    while sector_id < 0xFFFFFFF0 and sector_id not in seen_mini and len(mini_fat_blob) < _MAX_UNCOMPRESSED:
        seen_mini.add(sector_id)
        offset = sector_offset(sector_id)
        if offset < 0 or offset >= len(data):
            break
        mini_fat_blob += data[offset : offset + sector_size]
        sector_id = fat[sector_id] if sector_id < len(fat) else 0xFFFFFFFE
    mini_fat = [
        int.from_bytes(mini_fat_blob[index : index + 4], "little")
        for index in range(0, len(mini_fat_blob), 4)
    ]

    def read_mini(start: int, size: int) -> bytes:
        if start >= 0xFFFFFFF0 or size <= 0:
            return b""
        size = min(size, _MAX_UNCOMPRESSED)
        out = bytearray()
        sector_id = start
        seen: set[int] = set()
        while sector_id < 0xFFFFFFF0 and sector_id not in seen and len(out) < size:
            seen.add(sector_id)
            offset = sector_id * mini_size
            out.extend(mini_stream[offset : offset + mini_size])
            sector_id = mini_fat[sector_id] if sector_id < len(mini_fat) else 0xFFFFFFFE
        return bytes(out[:size])

    streams: dict[str, bytes] = {}
    for name, obj_type, start, size in entries:
        if obj_type != 2 or not name:
            continue
        if size < mini_cutoff:
            streams[name] = read_mini(start, size)
        else:
            streams[name] = read_chain(start, size)
    return streams


def _extract_pdf(data: bytes) -> str:
    if re.search(rb"/Encrypt\b", data[:65536]):
        raise ValueError("That PDF is encrypted. Export an unlocked copy and try again.")
    objects = _pdf_objects(data)
    cmaps: dict[int, dict[bytes, str]] = {}
    decoded: dict[int, bytes] = {}
    for obj_id, header, stream in objects:
        if stream is None:
            continue
        try:
            plain = _decode_pdf_stream(header, stream, objects)
        except (zlib.error, ValueError):
            continue
        decoded[obj_id] = plain
        if b"beginbfchar" in plain or b"beginbfrange" in plain:
            cmaps[obj_id] = _parse_cmap(plain.decode("latin-1", errors="replace"))
        if b"/Type" in header and b"/ObjStm" in header:
            for inner_id, inner_body in _parse_objstm(header, plain):
                objects.append((inner_id, inner_body, None))

    font_cmaps: dict[int, dict[bytes, str]] = {}
    for obj_id, header, _stream in objects:
        match = re.search(rb"/ToUnicode\s+(\d+)\s+\d+\s+R", header)
        if match:
            font_cmaps[obj_id] = cmaps.get(int(match.group(1)), {})

    content_fonts: dict[int, dict[str, dict[bytes, str]]] = {}
    for obj_id, header, _stream in objects:
        fonts = _font_map(header, font_cmaps)
        if not fonts:
            continue
        for content_id in _content_ids(header):
            content_fonts.setdefault(content_id, {}).update(fonts)
        if obj_id in decoded:
            content_fonts.setdefault(obj_id, {}).update(fonts)

    fallback = _merge_cmaps(cmaps.values())
    pieces: list[str] = []
    for obj_id, plain in decoded.items():
        header = next((item[1] for item in objects if item[0] == obj_id), b"")
        if b"/ObjStm" in header or b"/Image" in header or b"/ICCBased" in header:
            continue
        if b"Tj" not in plain and b"TJ" not in plain and b"BT" not in plain:
            continue
        fonts = content_fonts.get(obj_id) or {}
        pieces.append(_pdf_content_text(plain, fonts, fallback))
    return _reflow_wrapped_words("\n".join(piece for piece in pieces if piece.strip()))


def _reflow_wrapped_words(text: str) -> str:
    """Join a word that a PDF split across two visual lines."""
    return re.sub(r"([A-Za-z])\n([a-z])", r"\1\2", text)


def _pdf_objects(data: bytes) -> list[tuple[int, bytes, bytes | None]]:
    lengths = {
        int(obj_id): int(value)
        for obj_id, value in re.findall(rb"(\d+)\s+\d+\s+obj\s+(\d+)\s+endobj", data)
    }
    objects: list[tuple[int, bytes, bytes | None]] = []
    pattern = re.compile(rb"(\d+)\s+\d+\s+obj\b")
    index = 0
    while index < len(data):
        match = pattern.search(data, index)
        if not match:
            break
        obj_id = int(match.group(1))
        body_start = match.end()
        window_end = min(len(data), body_start + 12000)
        window = data[body_start:window_end]
        stream_at = window.find(b"stream")
        endobj_at = window.find(b"endobj")
        if stream_at != -1 and (endobj_at == -1 or stream_at < endobj_at):
            header = data[body_start : body_start + stream_at]
            content_start = body_start + stream_at + len(b"stream")
            if data[content_start : content_start + 2] == b"\r\n":
                content_start += 2
            elif content_start < len(data) and data[content_start] in (10, 13):
                content_start += 1
            length = _pdf_length(header, lengths)
            if length is None:
                endstream = data.find(b"endstream", content_start)
                if endstream == -1:
                    break
                stream = data[content_start:endstream]
                index = endstream + len(b"endstream")
            else:
                stream = data[content_start : content_start + length]
                index = content_start + length
            endobj = data.find(b"endobj", index)
            index = endobj + len(b"endobj") if endobj != -1 else index
            objects.append((obj_id, header, stream))
            continue
        endobj = data.find(b"endobj", body_start)
        if endobj == -1:
            break
        objects.append((obj_id, data[body_start:endobj], None))
        index = endobj + len(b"endobj")
    return objects


def _pdf_length(header: bytes, lengths: dict[int, int]) -> int | None:
    direct = re.search(rb"/Length\s+(\d+)\b", header)
    indirect = re.search(rb"/Length\s+(\d+)\s+\d+\s+R", header)
    if indirect:
        return lengths.get(int(indirect.group(1)))
    if direct:
        return int(direct.group(1))
    return None


def _decode_pdf_stream(header: bytes, stream: bytes, _objects: list) -> bytes:
    if re.search(rb"/Predictor\s+(?!1\b)\d+", header):
        return b""
    plain = stream
    for name in reversed(_pdf_filters(header)):
        if name == "FlateDecode":
            plain = _inflate(plain)
        elif name == "ASCII85Decode":
            plain = _ascii85(plain)
        elif name == "ASCIIHexDecode":
            plain = bytes.fromhex(re.sub(rb"[^0-9A-Fa-f]", b"", plain).decode("ascii") or "")
        elif name == "DCTDecode" or name == "JPXDecode" or name == "CCITTFaxDecode":
            return b""
        else:
            return b""
        if len(plain) > _MAX_UNCOMPRESSED:
            return plain[:_MAX_UNCOMPRESSED]
    return plain


def _pdf_filters(header: bytes) -> list[str]:
    array = re.search(rb"/Filter\s*\[(.*?)\]", header, re.S)
    if array:
        return [item.decode("ascii") for item in re.findall(rb"/([A-Za-z0-9]+)", array.group(1))]
    single = re.search(rb"/Filter\s*/([A-Za-z0-9]+)", header)
    if single:
        return [single.group(1).decode("ascii")]
    return []


def _inflate(data: bytes) -> bytes:
    for window_bits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            decompressor = zlib.decompressobj(window_bits)
            plain = decompressor.decompress(data, _MAX_UNCOMPRESSED)
            if len(plain) >= _MAX_UNCOMPRESSED:
                return plain[:_MAX_UNCOMPRESSED]
            return plain + decompressor.flush()
        except zlib.error:
            continue
    raise zlib.error("compressed stream could not be read")


def _ascii85(data: bytes) -> bytes:
    payload = data.strip()
    if not payload.endswith(b"~>"):
        payload += b"~>"
    return base64.a85decode(payload, adobe=True)


def _parse_cmap(text: str) -> dict[bytes, str]:
    mapping: dict[bytes, str] = {}
    for block in re.finditer(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block.group(1)):
            mapping[bytes.fromhex(src)] = _cmap_destination(dst)
    for block in re.finditer(r"beginbfrange(.*?)endbfrange", text, re.S):
        body = block.group(1)
        for src_start, src_end, dst in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
            body,
        ):
            width = max(1, len(src_start) // 2)
            start = int(src_start, 16)
            end = int(src_end, 16)
            dest = int(dst, 16)
            for offset, code in enumerate(range(start, min(end, start + 2000) + 1)):
                mapping[code.to_bytes(width, "big")] = _codepoint(dest + offset)
        for match in re.finditer(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]",
            body,
            re.S,
        ):
            start = int(match.group(1), 16)
            width = max(1, len(match.group(1)) // 2)
            for offset, dest in enumerate(re.findall(r"<([0-9A-Fa-f]+)>", match.group(3))):
                mapping[(start + offset).to_bytes(width, "big")] = _cmap_destination(dest)
    return mapping


def _cmap_destination(hex_text: str) -> str:
    raw = bytes.fromhex(hex_text)
    if len(raw) >= 2 and len(raw) % 2 == 0:
        return raw.decode("utf-16-be", errors="replace")
    return raw.decode("latin-1", errors="replace")


def _codepoint(value: int) -> str:
    if value < 0 or value > 0x10FFFF:
        return ""
    return chr(value)


def _parse_objstm(header: bytes, plain: bytes) -> list[tuple[int, bytes]]:
    count_match = re.search(rb"/N\s+(\d+)", header)
    first_match = re.search(rb"/First\s+(\d+)", header)
    if not count_match or not first_match:
        return []
    count = int(count_match.group(1))
    first = int(first_match.group(1))
    if count <= 0 or count > 5000 or first < 0 or first > len(plain):
        return []
    numbers = [int(item) for item in plain[:first].split()]
    pairs = list(zip(numbers[0::2], numbers[1::2]))[:count]
    body = plain[first:]
    inner: list[tuple[int, bytes]] = []
    for index, (obj_id, offset) in enumerate(pairs):
        if offset < 0 or offset > len(body):
            continue
        end = pairs[index + 1][1] if index + 1 < len(pairs) else len(body)
        inner.append((obj_id, body[offset:end]))
    return inner


def _font_map(header: bytes, font_cmaps: dict[int, dict[bytes, str]]) -> dict[str, dict[bytes, str]]:
    match = re.search(rb"/Font\s*<<", header)
    if not match:
        return {}
    start = match.end()
    depth = 1
    index = start
    while index < len(header) - 1 and depth:
        if header[index : index + 2] == b"<<":
            depth += 1
            index += 2
            continue
        if header[index : index + 2] == b">>":
            depth -= 1
            index += 2
            continue
        index += 1
    section = header[start : index - 2 if depth == 0 else index]
    fonts: dict[str, dict[bytes, str]] = {}
    for name, obj_id in re.findall(rb"/([A-Za-z0-9_.+-]+)\s+(\d+)\s+\d+\s+R", section):
        fonts[name.decode("ascii", errors="replace")] = font_cmaps.get(int(obj_id), {})
    return fonts


def _content_ids(header: bytes) -> list[int]:
    match = re.search(rb"/Contents\s*(\[.*?\]|\d+\s+\d+\s+R)", header, re.S)
    if not match:
        return []
    return [int(obj_id) for obj_id in re.findall(rb"(\d+)\s+\d+\s+R", match.group(1))]


def _merge_cmaps(groups) -> dict[bytes, str]:
    merged: dict[bytes, str] = {}
    for group in groups:
        for key, value in group.items():
            merged.setdefault(key, value)
    return merged


def _pdf_content_text(
    data: bytes,
    fonts: dict[str, dict[bytes, str]],
    fallback: dict[bytes, str],
) -> str:
    text = _show_text(data, fonts, fallback)
    if fallback and _readability(text) < 0.55:
        alt = _show_text(data, {}, fallback)
        if _readability(alt) > _readability(text):
            return alt
    return text


def _readability(text: str) -> float:
    stripped = text.strip()
    if not stripped:
        return 0.0
    good = sum(1 for char in stripped if char.isalnum() or char.isspace() or char in ".,;:'\"-?/&%")
    return good / len(stripped)


def _show_text(
    data: bytes,
    fonts: dict[str, dict[bytes, str]],
    fallback: dict[bytes, str],
) -> str:
    pieces: list[str] = []
    font_name: str | None = None
    args: list[tuple] = []
    array: list[tuple] | None = None
    for kind, value in _pdf_tokens(data):
        if kind == "[":
            array = []
            continue
        if kind == "]" and array is not None:
            args.append(("array", array))
            array = None
            continue
        if array is not None:
            array.append((kind, value))
            continue
        if kind != "op":
            args.append((kind, value))
            continue
        if value == "Tf" and len(args) >= 2 and args[-2][0] == "name":
            font_name = args[-2][1]
        elif value in {"Tj", "'"} and args and args[-1][0] == "str":
            if value == "'":
                pieces.append("\n")
            pieces.append(_decode_pdf_string(args[-1][1], font_name, fonts, fallback))
        elif value == '"' and args and args[-1][0] == "str":
            pieces.append("\n")
            pieces.append(_decode_pdf_string(args[-1][1], font_name, fonts, fallback))
        elif value == "TJ" and args and args[-1][0] == "array":
            for item_kind, item_value in args[-1][1]:
                if item_kind == "str":
                    pieces.append(_decode_pdf_string(item_value, font_name, fonts, fallback))
                elif item_kind == "num" and isinstance(item_value, (int, float)) and item_value < -120:
                    pieces.append(" ")
        elif value in {"T*", "Td", "TD"}:
            pieces.append("\n")
        elif value == "BT":
            pieces.append("\n")
        args = []
    return "".join(pieces)


def _decode_pdf_string(
    raw: bytes,
    font_name: str | None,
    fonts: dict[str, dict[bytes, str]],
    fallback: dict[bytes, str],
) -> str:
    if raw.startswith((b"\xfe\xff", b"\xff\xfe")):
        return raw.decode("utf-16", errors="replace").lstrip("\ufeff")
    cmap = fonts.get(font_name or "", {})
    if not cmap and len(fonts) == 1:
        cmap = next(iter(fonts.values()))
    if not cmap:
        cmap = fallback
    if cmap:
        mapped = _apply_cmap(raw, cmap)
        if _readability(mapped) >= 0.45:
            return mapped
    try:
        as_utf8 = raw.decode("utf-8")
    except UnicodeDecodeError:
        as_utf8 = ""
    if as_utf8 and _readability(as_utf8) >= 0.85:
        return as_utf8
    return raw.decode("latin-1", errors="replace")


def _apply_cmap(raw: bytes, cmap: dict[bytes, str]) -> str:
    widths = sorted({len(key) for key in cmap}, reverse=True)
    parts: list[str] = []
    index = 0
    while index < len(raw):
        matched = False
        for width in widths:
            chunk = raw[index : index + width]
            if chunk in cmap:
                parts.append(cmap[chunk])
                index += width
                matched = True
                break
        if not matched:
            parts.append(raw[index : index + 1].decode("latin-1", errors="replace"))
            index += 1
    return "".join(parts)


def _pdf_tokens(data: bytes):
    index = 0
    length = len(data)
    while index < length:
        current = data[index]
        if current in b" \t\r\n\x0c\x00":
            index += 1
            continue
        if current == ord("%"):
            newline = data.find(b"\n", index)
            index = length if newline == -1 else newline + 1
            continue
        if current == ord("("):
            literal, index = _read_literal(data, index)
            yield "str", literal
            continue
        if current == ord("<"):
            if data[index : index + 2] == b"<<":
                index = _skip_dict(data, index)
                continue
            literal, index = _read_hex(data, index)
            yield "str", literal
            continue
        if current == ord("["):
            yield "[", None
            index += 1
            continue
        if current == ord("]"):
            yield "]", None
            index += 1
            continue
        if current == ord("/"):
            end = index + 1
            while end < length and data[end] not in b" \t\r\n\x0c[]<>(){}/%":
                end += 1
            yield "name", data[index + 1 : end].decode("latin-1", errors="replace")
            index = end
            continue
        end = index
        while end < length and data[end] not in b" \t\r\n\x0c[]<>(){}/%":
            end += 1
        word = data[index:end]
        index = end
        try:
            if b"." in word or word in {b"+", b"-"}:
                yield "num", float(word)
            else:
                yield "num", int(word)
        except ValueError:
            yield "op", word.decode("latin-1", errors="replace")


def _read_literal(data: bytes, index: int) -> tuple[bytes, int]:
    index += 1
    out = bytearray()
    depth = 1
    while index < len(data) and depth:
        current = data[index]
        if current == ord("\\"):
            index += 1
            if index >= len(data):
                break
            escaped = data[index]
            mapped = {
                ord("n"): b"\n",
                ord("r"): b"\r",
                ord("t"): b"\t",
                ord("b"): b"\b",
                ord("f"): b"\f",
                ord("("): b"(",
                ord(")"): b")",
                ord("\\"): b"\\",
            }
            if escaped in mapped:
                out.extend(mapped[escaped])
                index += 1
            elif escaped in b"\r\n":
                if escaped == ord("\r") and index + 1 < len(data) and data[index + 1] == ord("\n"):
                    index += 2
                else:
                    index += 1
            elif chr(escaped) in "01234567":
                digits = bytearray([escaped])
                index += 1
                for _ in range(2):
                    if index < len(data) and chr(data[index]) in "01234567":
                        digits.append(data[index])
                        index += 1
                    else:
                        break
                out.append(int(digits, 8) & 0xFF)
            else:
                out.append(escaped)
                index += 1
            continue
        if current == ord("("):
            depth += 1
            out.append(current)
            index += 1
            continue
        if current == ord(")"):
            depth -= 1
            if depth == 0:
                index += 1
                break
            out.append(current)
            index += 1
            continue
        out.append(current)
        index += 1
    return bytes(out), index


def _read_hex(data: bytes, index: int) -> tuple[bytes, int]:
    index += 1
    chars: list[str] = []
    while index < len(data) and data[index] != ord(">"):
        if data[index] not in b" \t\r\n":
            chars.append(chr(data[index]))
        index += 1
    if index < len(data):
        index += 1
    if len(chars) % 2:
        chars.append("0")
    try:
        return bytes.fromhex("".join(chars)), index
    except ValueError:
        return b"", index


def _skip_dict(data: bytes, index: int) -> int:
    depth = 0
    while index < len(data) - 1:
        if data[index : index + 2] == b"<<":
            depth += 1
            index += 2
            continue
        if data[index : index + 2] == b">>":
            depth -= 1
            index += 2
            if depth == 0:
                return index
            continue
        if data[index] == ord("("):
            _, index = _read_literal(data, index)
            continue
        index += 1
    return len(data)
