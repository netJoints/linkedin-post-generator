"""The saved voice sample: saved once, reused, re-learned, and forgotten.

These tests point the sample folder at a temporary folder, so a real saved sample is never touched.
"""

import contextlib
import subprocess
import tempfile
from pathlib import Path

import pytest

import media
from media import ffmpeg_path, forget_my_voice, my_voice_status, save_my_voice, voice_catalog


def _tone(seconds: int) -> bytes:
    exe = ffmpeg_path()
    assert exe, "ffmpeg is needed for these tests"
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder, "tone.wav")
        subprocess.run(
            [exe, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", f"sine=frequency=220:duration={seconds}", str(out)],
            check=True,
        )
        return out.read_bytes()


@contextlib.contextmanager
def _own_folder():
    """Use a temporary sample folder for the duration of a test, then restore the real one."""
    saved = (media.MY_VOICE_DIR, media.MY_VOICE_FILE)
    with tempfile.TemporaryDirectory() as folder:
        media.MY_VOICE_DIR = Path(folder) / "my-voice"
        media.MY_VOICE_FILE = media.MY_VOICE_DIR / "reference.wav"
        try:
            yield media.MY_VOICE_FILE
        finally:
            media.MY_VOICE_DIR, media.MY_VOICE_FILE = saved


def test_a_saved_sample_is_kept_replaced_and_forgotten() -> None:
    with _own_folder() as sample:
        assert my_voice_status()["enrolled"] is False

        status = save_my_voice(_tone(6))
        assert status["enrolled"] is True
        assert 5.8 <= status["seconds"] <= 6.2
        assert sample.is_file()

        # Re-learn: a new recording replaces the old sample.
        status = save_my_voice(_tone(8))
        assert 7.8 <= status["seconds"] <= 8.2

        assert forget_my_voice()["enrolled"] is False
        assert not sample.exists()


def test_a_long_recording_is_kept_to_twenty_seconds() -> None:
    with _own_folder():
        status = save_my_voice(_tone(25))
        assert status["seconds"] <= media.MY_VOICE_KEEP_SECONDS + 0.2


def test_a_short_or_unreadable_recording_is_refused() -> None:
    with _own_folder() as sample:
        with pytest.raises(ValueError):
            save_my_voice(_tone(2))
        with pytest.raises(ValueError):
            save_my_voice(b"x" * 2000)
        assert not sample.exists()


def test_my_voice_is_listed_only_after_a_sample_is_saved() -> None:
    with _own_folder():
        ids = [name for name, _label in voice_catalog()]
        assert "chatterbox-clone" not in ids
        save_my_voice(_tone(6))
        ids = [name for name, _label in voice_catalog()]
        if media._chatterbox_ready():
            assert "chatterbox-clone" in ids


def test_my_voice_needs_a_saved_sample() -> None:
    with _own_folder():
        with pytest.raises(ValueError):
            media.speak("Hello there.", "chatterbox-clone")
