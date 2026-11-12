"""Picture videos keep a landscape frame, and the music bed stays quiet."""

import io
import subprocess
import wave

import pytest

from media import bed_wav, ffmpeg_path, join_videos, render_sequence, sequence_scale


def _jpeg(width: int, height: int) -> bytes:
    sof = (
        b"\xff\xc0\x00\x0b\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8" + sof + b"\xff\xd9"


def test_landscape_frames_keep_a_wide_scale() -> None:
    assert sequence_scale([_jpeg(1920, 1080)] * 8) == "scale=1920:1080:flags=lanczos,format=yuv420p"


def test_other_frames_stay_portrait() -> None:
    assert sequence_scale([_jpeg(1080, 1350)] * 8) == "scale=1080:1350:flags=lanczos,format=yuv420p"
    assert sequence_scale([_jpeg(160, 200)] * 8) == "scale=1080:1350:flags=lanczos,format=yuv420p"


def test_bed_peaks_under_a_tenth_of_full_scale() -> None:
    data = bed_wav(16)
    assert data[:4] == b"RIFF"
    with wave.open(io.BytesIO(data)) as handle:
        assert handle.getnchannels() == 2
        assert handle.getframerate() == 48000
        samples = memoryview(handle.readframes(handle.getnframes())).cast("h")
    peak = max(abs(sample) for sample in samples)
    assert 2000 <= peak <= 3200


def _clip(exe: str, width: int, height: int, color: str) -> bytes:
    frames = []
    for _ in range(8):
        completed = subprocess.run(
            [
                exe, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}",
                "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
            ],
            check=True,
            timeout=30,
            capture_output=True,
        )
        frames.append(completed.stdout)
    return render_sequence(frames[:1] * 16, 8)


def test_landscape_render_and_quiet_music() -> None:
    exe = ffmpeg_path()
    if not exe:
        pytest.skip("ffmpeg is not installed")
    video = join_videos([_clip(exe, 1920, 1080, "0x1b3ed2")], music=True)
    probe = exe.replace("ffmpeg", "ffprobe") if exe.endswith("ffmpeg") else "ffprobe"
    probed = subprocess.run(
        [
            probe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", "-",
        ],
        input=video,
        check=True,
        timeout=30,
        capture_output=True,
    )
    assert probed.stdout.decode().strip() == "1920,1080"
    measured = subprocess.run(
        [exe, "-hide_banner", "-i", "pipe:0", "-af", "volumedetect", "-f", "null", "-"],
        input=video,
        check=True,
        timeout=30,
        capture_output=True,
    )
    text = measured.stderr.decode()
    assert "max_volume:" in text
    loudness = float(text.split("max_volume:")[1].split("dB")[0].strip())
    assert -32 <= loudness <= -16
