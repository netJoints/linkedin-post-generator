"""Turn drawn frames into an MP4 on this laptop, when ffmpeg is installed."""

from __future__ import annotations

import array
import io
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

MAX_FRAMES = 10
MAX_MOTION_FRAMES = 160
MAX_FRAME_BYTES = 3_000_000
MAX_SCENE_VIDEOS = 10
MAX_SCENE_VIDEO_BYTES = 40_000_000
JPEG_PREFIX = b"\xff\xd8\xff"
PORTRAIT = (1080, 1350)
LANDSCAPE = (1920, 1080)
_SOF = {0xC0, 0xC1, 0xC2}
_STANDALONE = set(range(0xD0, 0xDA)) | {0x00, 0x01}
_LOOP_SECONDS = 16
_LOOP: array.array | None = None


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def parse_fps(value: str) -> int:
    if not str(value).isdigit():
        raise ValueError("The explainer could not be made. The card video is still available.")
    fps = int(value)
    if fps < 8 or fps > 12:
        raise ValueError("The explainer could not be made. The card video is still available.")
    return fps


def validate_frames(frames: list[bytes]) -> None:
    if not frames:
        raise ValueError("There are no cards to turn into a video.")
    if len(frames) > MAX_FRAMES:
        raise ValueError("Use 10 cards or fewer.")
    _check_jpegs(frames)


def validate_motion_frames(frames: list[bytes]) -> None:
    if len(frames) < 8:
        raise ValueError("The explainer did not have enough frames. The card video is still available.")
    if len(frames) > MAX_MOTION_FRAMES:
        raise ValueError("The explainer had too many frames. The card video is still available.")
    _check_jpegs(frames, motion=True)


def render_mp4(frames: list[bytes]) -> bytes:
    """Hold each card for 4 seconds. The command is fixed. Frame bytes are only image data."""
    validate_frames(frames)
    return _render(frames, "1/4", "card", "carousel.mp4", "linkedin-cards-")


def render_sequence(frames: list[bytes], fps: int) -> bytes:
    """Play each explainer frame at fps. The command is fixed. Frame bytes are only image data."""
    if fps < 8 or fps > 12:
        raise ValueError("The explainer could not be made. The card video is still available.")
    validate_motion_frames(frames)
    return _render(frames, str(fps), "frame", "explainer.mp4", "linkedin-motion-")


def join_videos(videos: list[bytes], music: bool = False) -> bytes:
    """Play the card videos one after another. Names are ours; the request supplies only bytes."""
    if not videos:
        raise ValueError("There are no card videos to join.")
    if len(videos) > MAX_SCENE_VIDEOS:
        raise ValueError(f"Join {MAX_SCENE_VIDEOS} cards or fewer.")
    for video in videos:
        if len(video) < 1000 or len(video) > MAX_SCENE_VIDEO_BYTES or b"ftyp" not in video[:32]:
            raise ValueError("A card video was not a valid MP4.")
    if len(videos) == 1 and not music:
        return videos[0]
    if len(videos) == 1:
        return _with_bed(videos[0])
    exe = ffmpeg_path()
    if not exe:
        raise ValueError("ffmpeg is not installed, so the cards could not be joined.")
    with tempfile.TemporaryDirectory(prefix="linkedin-join-") as folder:
        root = Path(folder)
        names = []
        for index, video in enumerate(videos, start=1):
            name = f"scene-{index:02d}.mp4"
            (root / name).write_bytes(video)
            names.append(f"file '{name}'")
        (root / "list.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
        out = root / "joined.mp4"
        leading = [exe, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt"]
        copied = [*leading, "-c", "copy", "-movflags", "+faststart", "joined.mp4"]
        encoded = [
            *leading,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            "joined.mp4",
        ]
        try:
            try:
                _run(copied, 120, root)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                out.unlink(missing_ok=True)
                _run(encoded, 300, root)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Joining the cards took too long.") from exc
        except subprocess.CalledProcessError as exc:
            raise ValueError("The cards could not be joined into one video.") from exc
        data = out.read_bytes() if out.is_file() else b""
    if len(data) < 1000 or b"ftyp" not in data[:32]:
        raise ValueError("The cards could not be joined into one video.")
    if music:
        return _with_bed(data)
    return data


def sequence_scale(frames: list[bytes]) -> str:
    """Scale to a fixed frame. Landscape stays 1920×1080. Everything else stays 1080×1350.

    The size comes from the JPEG header and is accepted only when every frame matches one of those two.
    The filter string is never built from request text.
    """
    size = _jpeg_size(frames[0]) if frames else None
    if size in (PORTRAIT, LANDSCAPE) and all(_jpeg_size(frame) == size for frame in frames):
        width, height = size
        return f"scale={width}:{height}:flags=lanczos,format=yuv420p"
    return "scale=1080:1350:flags=lanczos,format=yuv420p"


def bed_wav(duration: float) -> bytes:
    """An original quiet loop. The peak is held near one tenth of full scale."""
    seconds = min(180.0, max(1.0, float(duration)))
    loop = _music_loop()
    tiled = array.array("h")
    while len(tiled) < int(seconds * 48000) * 2:
        tiled.extend(loop)
    del tiled[int(seconds * 48000) * 2 :]
    handle = io.BytesIO()
    with wave.open(handle, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(48000)
        writer.writeframes(tiled.tobytes())
    return handle.getvalue()


def _music_loop() -> array.array:
    """Sixteen seconds, four chords, stereo. Built once, then reused."""
    global _LOOP
    if _LOOP is not None:
        return _LOOP
    rate = 48000
    chords = (
        (130.81, 164.81, 196.00),
        (110.00, 164.81, 220.00),
        (87.31, 130.81, 174.61),
        (98.00, 146.83, 196.00),
    )
    total = _LOOP_SECONDS * rate
    mono = array.array("f")
    for index in range(total):
        t = index / rate
        slot = int(t // 4) % 4
        local = t - (int(t // 4) * 4)
        edge = local if local < 0.45 else (4 - local if local > 3.55 else 0.45)
        env = min(1.0, edge / 0.45)
        freqs = chords[slot]
        pad = (
            math.sin(math.tau * freqs[0] * t)
            + math.sin(math.tau * freqs[1] * t)
            + math.sin(math.tau * freqs[2] * t)
        ) / 3
        beat = t - int(t)
        tick = math.sin(math.tau * 523.25 * t) * math.exp(-28 * beat) if beat < 0.18 else 0.0
        mono.append((pad * 0.75 * env) + (tick * 0.25))
    peak = max(abs(sample) for sample in mono) or 1.0
    scale = 0.09 * 32767 / peak
    stereo = array.array("h")
    for sample in mono:
        packed = int(max(-32767, min(32767, sample * scale)))
        stereo.append(packed)
        stereo.append(packed)
    _LOOP = stereo
    return stereo


def _with_bed(video: bytes) -> bytes:
    """Replace the silent track with the quiet bed. The picture frames are copied, not re-encoded."""
    exe = ffmpeg_path()
    if not exe:
        raise ValueError("ffmpeg is not installed, so the music could not be added.")
    with tempfile.TemporaryDirectory(prefix="linkedin-bed-") as folder:
        root = Path(folder)
        (root / "video.mp4").write_bytes(video)
        (root / "bed.wav").write_bytes(bed_wav(96))
        out = root / "with-bed.mp4"
        fade = "afade=t=in:st=0:d=1.2,areverse,afade=t=in:st=0:d=2,areverse"
        command = [
            exe, "-y", "-hide_banner", "-loglevel", "error",
            "-i", "video.mp4",
            "-i", "bed.wav",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "96k",
            "-af", fade,
            "-shortest",
            "-movflags", "+faststart",
            "with-bed.mp4",
        ]
        try:
            _run(command, 120, root)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError("The music could not be added to the video.") from exc
        data = out.read_bytes() if out.is_file() else b""
    if len(data) < 1000 or b"ftyp" not in data[:32]:
        raise ValueError("The music could not be added to the video.")
    return data


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10 or not data.startswith(JPEG_PREFIX):
        return None
    index = 2
    steps = 0
    while index + 8 < len(data) and steps < 40:
        steps += 1
        if data[index] != 0xFF:
            return None
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            return None
        marker = data[index]
        index += 1
        if marker in _STANDALONE:
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2 or index + length > len(data):
            return None
        if marker in _SOF and length >= 7:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            if width < 2 or height < 2:
                return None
            return width, height
        index += length
    return None


def _check_jpegs(frames: list[bytes], motion: bool = False) -> None:
    empty = "A frame was empty or too large." if motion else "A card image was empty or too large."
    kind = "Frames must be JPEG." if motion else "Card images must be JPEG."
    for frame in frames:
        if len(frame) < 100 or len(frame) > MAX_FRAME_BYTES:
            raise ValueError(empty)
        if not frame.startswith(JPEG_PREFIX):
            raise ValueError(kind)


def _render(frames: list[bytes], framerate: str, stem: str, filename: str, prefix: str) -> bytes:
    exe = ffmpeg_path()
    if not exe:
        raise ValueError(
            "ffmpeg is not installed, so the video could not be made. The PDF and the images are still available."
        )
    width = 3 if stem == "frame" else 2
    with tempfile.TemporaryDirectory(prefix=prefix) as folder:
        root = Path(folder)
        for index, frame in enumerate(frames, start=1):
            (root / f"{stem}-{index:0{width}d}.jpg").write_bytes(frame)
        out = root / filename
        pattern = str(root / f"{stem}-%0{width}d.jpg")
        # Frame bytes are image files we just wrote. The command does not take names from the request.
        leading = [exe, "-y", "-hide_banner", "-loglevel", "error", "-framerate", framerate, "-i", pattern]
        encoding = [
            "-vf",
            sequence_scale(frames),
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-movflags",
            "+faststart",
            str(out),
        ]
        with_audio = [
            *leading,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            *encoding,
        ]
        try:
            try:
                _run(with_audio, 180 if stem == "frame" else 120)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                _run([*leading, *encoding], 180 if stem == "frame" else 120)
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                "The video took too long to make. The PDF and the images are still available."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ValueError(
                "The video could not be made. The PDF and the images are still available."
            ) from exc
        data = out.read_bytes() if out.is_file() else b""
    if len(data) < 1000 or b"ftyp" not in data[:32]:
        raise ValueError("The video could not be made. The PDF and the images are still available.")
    return data


def _run(command: list[str], timeout: int, cwd: Path | None = None) -> None:
    subprocess.run(command, check=True, timeout=timeout, capture_output=True, cwd=cwd)
