"""Picture videos keep a landscape frame, and the chosen track stays quiet."""

import subprocess

import pytest

from media import ffmpeg_path, join_videos, music_path, render_sequence, sequence_scale, speak


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


def test_music_slug_is_a_known_file() -> None:
    path = music_path("river")
    assert path is not None and path.name == "river.m4a"
    assert music_path("quiet") is None
    assert music_path("../server") is None
    assert music_path("river.m4a") is None


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
    video = join_videos([_clip(exe, 1920, 1080, "0x1b3ed2")], music="river")
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


def _tone(exe: str) -> bytes:
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "tone.m4a"
        subprocess.run(
            [
                exe, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                "-c:a", "aac", str(out),
            ],
            check=True,
            timeout=30,
            capture_output=True,
        )
        return out.read_bytes()


def test_voiceover_keeps_the_picture_length() -> None:
    exe = ffmpeg_path()
    if not exe:
        pytest.skip("ffmpeg is not installed")
    video = join_videos([_clip(exe, 1920, 1080, "0x1b3ed2")], voice=_tone(exe), voice_level="normal")
    probe = exe.replace("ffmpeg", "ffprobe") if exe.endswith("ffmpeg") else "ffprobe"
    probed = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "-"],
        input=video,
        check=True,
        timeout=30,
        capture_output=True,
    )
    duration = float(probed.stdout.decode().strip())
    assert 1.6 <= duration <= 2.6
    with pytest.raises(ValueError):
        join_videos([_clip(exe, 1080, 1350, "0x102c44")], voice=b"not-audio" * 40)


def test_speech_rejects_an_unknown_voice() -> None:
    with pytest.raises(ValueError):
        speak("Hello from the laptop.", "../Samantha")
    spoken = speak("Hello from the laptop.", "af_heart")
    assert spoken.startswith(b"RIFF")
