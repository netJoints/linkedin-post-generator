"""Turn the card images into an MP4 on this laptop, when ffmpeg is installed."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_FRAMES = 10
MAX_FRAME_BYTES = 3_000_000
JPEG_PREFIX = b"\xff\xd8\xff"


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def validate_frames(frames: list[bytes]) -> None:
    if not frames:
        raise ValueError("There are no cards to turn into a video.")
    if len(frames) > MAX_FRAMES:
        raise ValueError("Use 10 cards or fewer.")
    for frame in frames:
        if len(frame) < 100 or len(frame) > MAX_FRAME_BYTES:
            raise ValueError("A card image was empty or too large.")
        if not frame.startswith(JPEG_PREFIX):
            raise ValueError("Card images must be JPEG.")


def render_mp4(frames: list[bytes]) -> bytes:
    """Hold each card for 4 seconds. The command is fixed. Frame bytes are only image data."""
    exe = ffmpeg_path()
    if not exe:
        raise ValueError(
            "ffmpeg is not installed, so the video could not be made. The PDF and the images are still available."
        )
    validate_frames(frames)
    with tempfile.TemporaryDirectory(prefix="linkedin-cards-") as folder:
        root = Path(folder)
        for index, frame in enumerate(frames, start=1):
            (root / f"card-{index:02d}.jpg").write_bytes(frame)
        out = root / "carousel.mp4"
        pattern = str(root / "card-%02d.jpg")
        leading = [exe, "-y", "-hide_banner", "-loglevel", "error", "-framerate", "1/4", "-i", pattern]
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
                _run(with_audio)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                _run([*leading, *encoding])
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


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, timeout=120, capture_output=True)
