"""Turn still pictures, each with a caption drawn in the browser, into one portrait MP4.

The request supplies image bytes only. A filename is an order number, never a path.
Caption words are already pixels in the overlay, so they are not placed on a command line.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

from media import ffmpeg_path

MAX_STILLS = 12
MAX_STILL_BYTES = 2_500_000
MAX_OVERLAY_BYTES = 2_000_000
MAX_EDGE = 8_000
MAX_PIXELS = 24_000_000
SHOT_SECONDS = 3.6
FADE_SECONDS = 0.4
FPS = 30
WIDTH = 1080
HEIGHT = 1350
STAGE_W = 1296
STAGE_H = 1620
JPEG_PREFIX = b"\xff\xd8\xff"
PNG_PREFIX = b"\x89PNG\r\n\x1a\n"
_STILL_NAME = re.compile(r"still-(\d+)\.jpe?g$", re.I)
_CAPTION_NAME = re.compile(r"caption-(\d+)\.png$", re.I)
_SOF = {0xC0, 0xC1, 0xC2}
_STANDALONE = set(range(0xD0, 0xDA)) | {0x00, 0x01}


def check_still(data: bytes) -> None:
    """Accept a JPEG small enough to decode, and reject a size we did not ask for."""
    if len(data) < 100 or len(data) > MAX_STILL_BYTES or not data.startswith(JPEG_PREFIX):
        raise ValueError("One picture could not be read. Use a JPEG, PNG, WEBP, GIF, or SVG.")
    width, height = _jpeg_size(data)
    if width < 2 or height < 2 or width > MAX_EDGE or height > MAX_EDGE or width * height > MAX_PIXELS:
        raise ValueError("One picture could not be read. Use a JPEG, PNG, WEBP, GIF, or SVG.")


def check_overlay(data: bytes) -> None:
    """The caption is a PNG the page drew at the video size. Anything else is refused."""
    if len(data) < 24 or len(data) > MAX_OVERLAY_BYTES or not data.startswith(PNG_PREFIX):
        raise ValueError("A caption could not be read.")
    if data[12:16] != b"IHDR":
        raise ValueError("A caption could not be read.")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width != WIDTH or height != HEIGHT:
        raise ValueError("A caption could not be read.")


def stills_from_multipart(content_type: str, body: bytes) -> list[tuple[bytes, bytes | None]]:
    """Pair each picture with its caption overlay. Order comes from the number, not the upload order."""
    match = re.search(r'boundary="?([^";]+)"?', content_type, re.I)
    if not match:
        raise ValueError("The pictures were not valid.")
    boundary = match.group(1).encode("utf-8", errors="strict")
    if not boundary or len(boundary) > 200 or b"\r" in boundary or b"\n" in boundary:
        raise ValueError("The pictures were not valid.")
    stills: dict[int, bytes] = {}
    captions: dict[int, bytes] = {}
    for headers, content in _split_multipart(body, boundary):
        filename = _filename(headers.get("content-disposition", ""))
        if filename is None:
            raise ValueError("The pictures were not valid.")
        still_match = _STILL_NAME.fullmatch(filename)
        caption_match = _CAPTION_NAME.fullmatch(filename)
        if still_match:
            number = int(still_match.group(1))
            if number < 1 or number > MAX_STILLS or number in stills:
                raise ValueError(f"Use {MAX_STILLS} pictures or fewer.")
            check_still(content)
            stills[number] = content
        elif caption_match:
            number = int(caption_match.group(1))
            if number < 1 or number > MAX_STILLS or number in captions:
                raise ValueError("A caption could not be read.")
            check_overlay(content)
            captions[number] = content
        else:
            raise ValueError("The pictures were not valid.")
        if len(stills) > MAX_STILLS:
            raise ValueError(f"Use {MAX_STILLS} pictures or fewer.")
    if not stills:
        raise ValueError("Add at least one picture.")
    if any(number not in stills for number in captions):
        raise ValueError("A caption could not be read.")
    return [(stills[number], captions.get(number)) for number in sorted(stills)]


def render_stills(shots: list[tuple[bytes, bytes | None]]) -> bytes:
    """Hold each picture for about 3.5 seconds, with a short move, then crossfade."""
    if not shots:
        raise ValueError("Add at least one picture.")
    if len(shots) > MAX_STILLS:
        raise ValueError(f"Use {MAX_STILLS} pictures or fewer.")
    for still, overlay in shots:
        check_still(still)
        if overlay is not None:
            check_overlay(overlay)
    exe = ffmpeg_path()
    if not exe:
        raise ValueError("ffmpeg is not installed, so the video could not be made.")
    frames = round(SHOT_SECONDS * FPS)
    duration = frames / FPS
    with tempfile.TemporaryDirectory(prefix="linkedin-stills-") as folder:
        root = Path(folder)
        segments: list[Path] = []
        try:
            for index, (still, overlay) in enumerate(shots, start=1):
                still_path = root / f"still-{index:02d}.jpg"
                overlay_path = root / f"caption-{index:02d}.png"
                still_path.write_bytes(still)
                if overlay is not None:
                    overlay_path.write_bytes(overlay)
                segment = root / f"seg-{index:02d}.mp4"
                _segment(exe, still_path, overlay_path if overlay is not None else None, segment, index - 1, frames)
                segments.append(segment)
            out = root / "picture-video.mp4"
            _join(exe, segments, out, duration)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("The video took too long to make.") from exc
        except subprocess.CalledProcessError as exc:
            raise ValueError("The video could not be made.") from exc
        data = out.read_bytes() if out.is_file() else b""
    if len(data) < 1000 or b"ftyp" not in data[:32]:
        raise ValueError("The video could not be made.")
    return data


def _jpeg_size(data: bytes) -> tuple[int, int]:
    index = 2
    steps = 0
    while index + 8 < len(data) and steps < 200:
        steps += 1
        if data[index] != 0xFF:
            break
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            break
        marker = data[index]
        index += 1
        if marker in _STANDALONE:
            continue
        if index + 2 > len(data):
            break
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2 or index + length > len(data):
            break
        if marker in _SOF and length >= 7:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += length
    raise ValueError("One picture could not be read. Use a JPEG, PNG, WEBP, GIF, or SVG.")


def _filename(header: str) -> str | None:
    if not re.search(r"filename\s*=", header, re.I):
        return None
    starred = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", header, re.I)
    if starred:
        name = urllib.parse.unquote(starred.group(1).strip().strip('"'))
    else:
        match = re.search(r'(?:^|;)\s*filename="([^"]*)"', header, re.I)
        if match:
            name = match.group(1)
        else:
            match = re.search(r"(?:^|;)\s*filename=([^;]+)", header, re.I)
            name = match.group(1).strip().strip('"') if match else ""
    # Only the final path piece can match still-01.jpg. A directory prefix cannot.
    return name.replace("\\", "/").rsplit("/", 1)[-1]


def _split_multipart(body: bytes, boundary: bytes):
    delimiter = b"--" + boundary
    for chunk in body.split(delimiter):
        if not chunk or chunk.startswith(b"--"):
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        elif chunk.endswith(b"\n"):
            chunk = chunk[:-1]
        header_blob, separator, content = chunk.partition(b"\r\n\r\n")
        if not separator:
            header_blob, separator, content = chunk.partition(b"\n\n")
        if not separator:
            continue
        headers: dict[str, str] = {}
        for line in header_blob.decode("utf-8", errors="replace").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        yield headers, content


def _ease() -> str:
    return f"(0.5-0.5*cos(PI*t/{SHOT_SECONDS:.5f}))"


def _segment(
    exe: str,
    still: Path,
    overlay: Path | None,
    dest: Path,
    index: int,
    frames: int,
) -> None:
    ease = _ease()
    anchor = f"(0.38+0.24*{ease})" if index % 2 == 0 else f"(0.62-0.24*{ease})"
    crop = (
        f"crop=w='if(isnan(t),{STAGE_W},trunc(({STAGE_W}-104*{ease})/2)*2)':"
        f"h='if(isnan(t),{STAGE_H},trunc(({STAGE_H}-130*{ease})/2)*2)':"
        f"x='if(isnan(t),0,min(max(0,(in_w-out_w)*{anchor}),in_w-out_w))':"
        f"y='if(isnan(t),0,(in_h-out_h)/2)'"
    )
    graph = (
        f"[0:v]scale={STAGE_W}:{STAGE_H}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={STAGE_W}:{STAGE_H},{crop},"
        f"scale={WIDTH}:{HEIGHT}:flags=lanczos:in_range=pc:out_range=tv,setsar=1,fps={FPS},format=yuv420p[base]"
    )
    if overlay is not None:
        graph += ";[1:v]format=rgba[cap];[base][cap]overlay=0:0:format=auto,format=yuv420p[v]"
    else:
        graph += ";[base]format=yuv420p[v]"
    command = [
        exe, "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-i", still.name,
    ]
    if overlay is not None:
        command += ["-loop", "1", "-framerate", str(FPS), "-i", overlay.name]
    command += [
        "-filter_complex", graph,
        "-map", "[v]",
        "-frames:v", str(frames),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "16",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        dest.name,
    ]
    subprocess.run(command, check=True, timeout=60, capture_output=True, cwd=still.parent)


def _join(exe: str, segments: list[Path], dest: Path, shot_seconds: float) -> None:
    total = shot_seconds * len(segments) - FADE_SECONDS * (len(segments) - 1)
    fade_out = max(0.2, total - 0.45)
    if len(segments) == 1:
        video = f"[0:v]fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.40,format=yuv420p[v]"
    else:
        parts = []
        acc = shot_seconds
        current = "[0:v]"
        for index in range(1, len(segments)):
            offset = acc - FADE_SECONDS
            label = f"[x{index}]" if index < len(segments) - 1 else "[xf]"
            parts.append(
                f"{current}[{index}:v]xfade=transition=fade:duration={FADE_SECONDS}:offset={offset:.5f}{label}"
            )
            acc += shot_seconds - FADE_SECONDS
            current = label
        video = ";".join(parts) + f";[xf]fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.40,format=yuv420p[v]"
    command = [exe, "-y", "-hide_banner", "-loglevel", "error"]
    for segment in segments:
        command += ["-i", segment.name]
    command += [
        "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}",
        "-filter_complex", video + ";[v]format=yuv420p[out]",
        "-map", "[out]",
        "-map", f"{len(segments)}:a:0",
        "-shortest",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
        "-c:a", "aac",
        "-b:a", "96k",
        "-movflags", "+faststart",
        dest.name,
    ]
    subprocess.run(command, check=True, timeout=120, capture_output=True, cwd=segments[0].parent)
