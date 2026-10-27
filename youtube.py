"""Read a YouTube transcript on this machine. No API key and no saved cookies.

The watch page usually has no caption text, and YouTube often answers it with
HTTP 429. The player endpoint still lists caption tracks. This module asks for
those tracks, then downloads one caption file. A caption address is opened only
when its host is YouTube or Google video, and only after the same public-address
check used for other links.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

TRANSCRIPT_TEXT_LIMIT = 8_000
_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
_ANDROID_UA = "com.google.android.youtube/20.10.38 (Linux; U; Android 14)"
_TIMEOUT = 12
_PLAYER_BYTES = 2_000_000
_PAGE_BYTES = 2_000_000
_CAPTION_BYTES = 1_000_000
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PAGE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_CAPTION_HOSTS = _PAGE_HOSTS | {"youtu.be"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def youtube_video_id(url: str) -> str | None:
    """Return the 11-character video id, or None when the link is not one video."""
    parsed = urllib.parse.urlparse(url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate if _VIDEO_ID.fullmatch(candidate) else None
    if host not in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        return None
    query_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
    if _VIDEO_ID.fullmatch(query_id):
        return query_id
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"} and _VIDEO_ID.fullmatch(parts[1]):
        return parts[1]
    return None


def fetch_transcript(video_id: str) -> str:
    """Return plain transcript text, capped. Raises ValueError when none is available."""
    if not _VIDEO_ID.fullmatch(video_id):
        raise ValueError("That YouTube link does not point at one video.")
    tracks: list[dict] = []
    for loader in (_android_tracks, _watch_tracks):
        try:
            tracks = loader(video_id)
        except (ValueError, json.JSONDecodeError, TimeoutError, OSError):
            tracks = []
        if tracks:
            break
    if not tracks:
        raise ValueError("YouTube did not provide a transcript for that video.")
    try:
        raw = _fetch(
            _track_url(_pick_track(tracks)),
            headers={"User-Agent": _ANDROID_UA, "Accept-Language": "en-US,en;q=0.9"},
            limit=_CAPTION_BYTES,
            allow_host=_caption_host,
        )
        text = _parse_caption(raw)
    except (ValueError, json.JSONDecodeError, ET.ParseError, TimeoutError, OSError) as exc:
        raise ValueError("YouTube did not provide a transcript for that video.") from exc
    if not text:
        raise ValueError("YouTube did not provide a transcript for that video.")
    return _cap(text, TRANSCRIPT_TEXT_LIMIT)


def _android_tracks(video_id: str) -> list[dict]:
    payload = {
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "20.10.38",
                "hl": "en",
                "gl": "US",
            }
        },
        "videoId": video_id,
    }
    body = _fetch(
        _PLAYER_URL,
        headers={"Content-Type": "application/json", "User-Agent": _ANDROID_UA},
        limit=_PLAYER_BYTES,
        allow_host=_page_host,
        data=json.dumps(payload).encode("utf-8"),
    )
    parsed = json.loads(body.decode("utf-8", errors="replace"))
    if not isinstance(parsed, dict):
        return []
    captions = parsed.get("captions") or {}
    renderer = captions.get("playerCaptionsTracklistRenderer") or {}
    tracks = renderer.get("captionTracks") or []
    if not isinstance(tracks, list):
        return []
    return [track for track in tracks if isinstance(track, dict) and track.get("baseUrl")]


def _watch_tracks(video_id: str) -> list[dict]:
    """Same caption list the summary tool reads from the watch page, when YouTube serves it."""
    page_url = f"https://www.youtube.com/watch?v={video_id}"
    body = _fetch(
        page_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
            # Skips the consent interstitial. This is not a session cookie.
            "Cookie": "SOCS=CAI",
        },
        limit=_PAGE_BYTES,
        allow_host=_page_host,
    )
    page = body.decode("utf-8", errors="replace")
    for payload in _player_blobs(page):
        captions = payload.get("captions") or {}
        renderer = captions.get("playerCaptionsTracklistRenderer") or {}
        tracks = renderer.get("captionTracks") or []
        chosen = [track for track in tracks if isinstance(track, dict) and track.get("baseUrl")]
        if chosen:
            return chosen
    return []


def _player_blobs(page: str) -> list[dict]:
    found: list[dict] = []
    decoder = json.JSONDecoder()
    marker = "ytInitialPlayerResponse"
    start = 0
    while True:
        at = page.find(marker, start)
        if at == -1:
            break
        brace = page.find("{", at)
        if brace == -1:
            break
        try:
            payload, end = decoder.raw_decode(page[brace:])
        except json.JSONDecodeError:
            start = at + len(marker)
            continue
        if isinstance(payload, dict):
            found.append(payload)
        start = brace + max(end, 1)
    return found


def _pick_track(tracks: list[dict]) -> dict:
    ranked: list[tuple[int, int, dict]] = []
    for track in tracks:
        if not track.get("baseUrl"):
            continue
        code = str(track.get("languageCode", "")).lower()
        english = code == "en" or code.startswith("en-")
        generated = 1 if track.get("kind") == "asr" else 0
        ranked.append((0 if english else 1, generated, track))
    if not ranked:
        raise ValueError("YouTube did not provide a transcript for that video.")
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked[0][2]


def _track_url(track: dict) -> str:
    base = str(track.get("baseUrl") or "").strip()
    if base.startswith("//"):
        base = "https:" + base
    if not base.startswith("https://"):
        raise ValueError("That caption address is not a YouTube host.")
    return base


def _page_host(host: str) -> bool:
    return host.lower().rstrip(".") in _PAGE_HOSTS


def _caption_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    if host in _CAPTION_HOSTS or host in _PAGE_HOSTS:
        return True
    return host == "googlevideo.com" or host.endswith(".googlevideo.com")


def _fetch(url: str, *, headers: dict[str, str], limit: int, allow_host, data: bytes | None = None) -> bytes:
    from server import validate_public_url

    opener = urllib.request.build_opener(_NoRedirect)
    current = validate_public_url(url)
    for _ in range(4):
        parsed = urllib.parse.urlparse(current)
        if parsed.scheme != "https" or not allow_host(parsed.hostname or ""):
            raise ValueError("That caption address is not a YouTube host.")
        request = urllib.request.Request(current, data=data, headers=headers)
        try:
            response = opener.open(request, timeout=_TIMEOUT)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"YouTube returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise ValueError("Could not reach YouTube.") from exc
        status = getattr(response, "status", 200)
        if status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("YouTube redirected without a destination.")
            current = validate_public_url(urllib.parse.urljoin(current, location))
            data = None
            continue
        with response:
            body = response.read(limit + 1)
        return body[:limit]
    raise ValueError("YouTube redirected too many times.")


def _parse_caption(data: bytes) -> str:
    stripped = data.lstrip()
    if not stripped:
        return ""
    folded = stripped.lower()
    if b"<!doctype" in folded or b"<!entity" in folded:
        raise ValueError("That caption file is not a plain transcript.")
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        return _json_caption(stripped)
    return _xml_caption(stripped)


def _json_caption(data: bytes) -> str:
    payload = json.loads(data.decode("utf-8", errors="replace"))
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        return ""
    lines: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        for seg in event.get("segs") or []:
            if isinstance(seg, dict) and seg.get("utf8"):
                lines.append(str(seg["utf8"]))
    return _collapse(html.unescape("".join(lines)))


def _xml_caption(data: bytes) -> str:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("That caption file is not a plain transcript.") from exc
    lines: list[str] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in {"text", "p"}:
            continue
        chunk = "".join(element.itertext())
        if chunk.strip():
            lines.append(html.unescape(chunk))
    return _collapse(" ".join(lines))


def _collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    shortened = text[:limit].rsplit(" ", 1)[0].strip()
    body = shortened or text[:limit].strip()
    return body + " [Transcript truncated.]"
