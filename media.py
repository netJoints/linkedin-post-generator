"""Turn drawn frames into an MP4 on this laptop, when ffmpeg is installed."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_FRAMES = 10
MAX_MOTION_FRAMES = 160
MAX_FRAME_BYTES = 3_000_000
JPEG_PREFIX = b"\xff\xd8\xff"


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
            "scale=1080:1350:flags=lanczos,format=yuv420p",
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


def _run(command: list[str], timeout: int) -> None:
    subprocess.run(command, check=True, timeout=timeout, capture_output=True)
