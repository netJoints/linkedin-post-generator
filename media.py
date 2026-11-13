"""Turn drawn frames into an MP4 on this laptop, when ffmpeg is installed."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import wave
from datetime import datetime
from pathlib import Path

MAX_FRAMES = 10
MAX_MOTION_FRAMES = 160
MAX_FRAME_BYTES = 3_000_000
MAX_SCENE_VIDEOS = 10
MAX_SCENE_VIDEO_BYTES = 40_000_000
MAX_VOICE_BYTES = 12_000_000
JPEG_PREFIX = b"\xff\xd8\xff"
PORTRAIT = (1080, 1350)
LANDSCAPE = (1920, 1080)
_SOF = {0xC0, 0xC1, 0xC2}
_STANDALONE = set(range(0xD0, 0xDA)) | {0x00, 0x01}
MUSIC_DIR = Path(__file__).resolve().parent / "static" / "music"
# Public-domain FreePD tracks. The slug is the filename and the only accepted music value.
MUSIC_TRACKS = {
    "beat": "Meditating Beat",
    "river": "River Meditation",
    "inspiration": "Inspiration",
    "inventing": "Inventing Flight",
    "energizing": "Energizing",
    "celebration": "Celebration",
}


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


def music_path(slug: str) -> Path | None:
    """A bundled track, or nothing. The slug must be a catalog key, never a path."""
    if slug not in MUSIC_TRACKS:
        return None
    root = MUSIC_DIR.resolve()
    path = (root / f"{slug}.m4a").resolve()
    if path.parent != root or not path.is_file():
        return None
    return path


MUSIC_LEVELS = {"low": 0.06, "medium": 0.12, "high": 0.22}
# Loudness targets for a voiceover. The filter string is chosen from this map, never built from request text.
VOICE_LEVELS = {
    "soft": "highpass=f=90,loudnorm=I=-20:TP=-2:LRA=7",
    "normal": "highpass=f=90,loudnorm=I=-17:TP=-1.5:LRA=7",
    "strong": "highpass=f=90,loudnorm=I=-14:TP=-1.5:LRA=7",
}
# Local AI voices. Each engine has its own environment under ~/.linkedin-tts, and its helper
# script runs with that environment's Python. Nothing here sends the post to a cloud service.
LOCAL_TTS_HOME = Path.home() / ".linkedin-tts"
KOKORO_PYTHON = LOCAL_TTS_HOME / "venv" / "bin" / "python"
KOKORO_MODEL = LOCAL_TTS_HOME / "kokoro-v1.0.onnx"
KOKORO_HELPER = Path(__file__).resolve().parent / "tts_kokoro.py"
CHATTERBOX_PYTHON = LOCAL_TTS_HOME / "chatterbox-venv" / "bin" / "python"
CHATTERBOX_HELPER = Path(__file__).resolve().parent / "tts_chatterbox.py"
CHATTERBOX_CACHE = Path.home() / ".cache" / "huggingface" / "hub" / "models--ResembleAI--chatterbox"
KOKORO_VOICES = (
    ("af_heart", "Heart, US"),
    ("af_bella", "Bella, US"),
    ("af_nicole", "Nicole, US"),
    ("am_michael", "Michael, US"),
    ("bf_emma", "Emma, UK"),
    ("bm_george", "George, UK"),
)
CHATTERBOX_VOICE = ("chatterbox", "Chatterbox, default voice")
CHATTERBOX_CLONE = ("chatterbox-clone", "Chatterbox, my voice")
VOICE_CHOICES = KOKORO_VOICES + (CHATTERBOX_VOICE, CHATTERBOX_CLONE)
CHATTERBOX_TIMEOUT = 1800

# The one voice sample of the user. Saved once, reused for every video, replaced when re-learned.
# It lives outside the repo, so it is never committed.
MY_VOICE_DIR = LOCAL_TTS_HOME / "my-voice"
MY_VOICE_FILE = MY_VOICE_DIR / "reference.wav"
MY_VOICE_MIN_SECONDS = 5.0
MY_VOICE_KEEP_SECONDS = 20


def voice_catalog() -> list[tuple[str, str]]:
    """The voices whose files are on this laptop. My voice appears only after a sample is saved."""
    voices: list[tuple[str, str]] = []
    if _kokoro_ready():
        voices.extend(KOKORO_VOICES)
    if _chatterbox_ready():
        voices.append(CHATTERBOX_VOICE)
        if MY_VOICE_FILE.is_file():
            voices.append(CHATTERBOX_CLONE)
    return voices


def _kokoro_ready() -> bool:
    return KOKORO_PYTHON.is_file() and KOKORO_HELPER.is_file() and KOKORO_MODEL.is_file()


def _chatterbox_ready() -> bool:
    return CHATTERBOX_PYTHON.is_file() and CHATTERBOX_HELPER.is_file() and CHATTERBOX_CACHE.is_dir()


def speak(text: str, voice: str) -> bytes:
    """Read the post aloud with a local AI voice. The voice must be on VOICE_CHOICES.

    The text goes in on stdin, never on a command line. My voice reads the saved sample.
    """
    speech = _speech_text(text)
    if voice not in {name for name, _label in VOICE_CHOICES}:
        raise ValueError("Choose a voice from the list.")
    if voice in {name for name, _label in KOKORO_VOICES}:
        if not _kokoro_ready():
            raise ValueError("The Kokoro voice is not installed yet, so the post cannot be read aloud.")
        return _speech_from_helper([str(KOKORO_PYTHON), str(KOKORO_HELPER)], {"text": speech, "voice": voice}, 300)
    if not _chatterbox_ready():
        raise ValueError("The Chatterbox voice is not installed yet, so the post cannot be read aloud.")
    if voice == CHATTERBOX_CLONE[0]:
        if not MY_VOICE_FILE.is_file():
            raise ValueError("Save your voice sample first, then choose My voice.")
        args = [str(CHATTERBOX_PYTHON), str(CHATTERBOX_HELPER), "clone", str(MY_VOICE_FILE)]
    else:
        args = [str(CHATTERBOX_PYTHON), str(CHATTERBOX_HELPER), "default"]
    return _speech_from_helper(args, {"text": speech}, CHATTERBOX_TIMEOUT)


def _speech_from_helper(args: list[str], payload: dict, timeout: int) -> bytes:
    try:
        completed = subprocess.run(
            args,
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("The post could not be read aloud.") from exc
    data = completed.stdout
    if len(data) < 100 or not data.startswith(b"RIFF"):
        raise ValueError("The post could not be read aloud.")
    return data


def my_voice_status() -> dict:
    """Whether a voice sample is saved, how long it is, and when it was last saved."""
    if not MY_VOICE_FILE.is_file():
        return {"enrolled": False, "seconds": None, "updated": None}
    try:
        seconds = _wav_seconds(MY_VOICE_FILE)
    except (wave.Error, OSError):
        return {"enrolled": False, "seconds": None, "updated": None}
    updated = datetime.fromtimestamp(MY_VOICE_FILE.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return {"enrolled": True, "seconds": round(seconds, 1), "updated": updated}


def save_my_voice(recording: bytes) -> dict:
    """Save the voice sample. Saving again replaces the old one, which is how the voice is re-learned."""
    if len(recording) < 1000 or len(recording) > MAX_VOICE_BYTES:
        raise ValueError("That recording is empty or too large.")
    exe = ffmpeg_path()
    if not exe:
        raise ValueError("ffmpeg is not installed, so the voice sample cannot be saved.")
    MY_VOICE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="linkedin-my-voice-") as folder:
        root = Path(folder)
        (root / "recording.bin").write_bytes(recording)
        try:
            _run(
                [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", "recording.bin",
                 "-vn", "-ac", "1", "-ar", "24000", "-t", str(MY_VOICE_KEEP_SECONDS),
                 "-c:a", "pcm_s16le", "sample.wav"],
                120,
                root,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError("That file could not be read as audio.") from exc
        sample = root / "sample.wav"
        try:
            seconds = _wav_seconds(sample)
        except (wave.Error, OSError) as exc:
            raise ValueError("That file could not be read as audio.") from exc
        if seconds < MY_VOICE_MIN_SECONDS:
            raise ValueError(f"Record at least {MY_VOICE_MIN_SECONDS:.0f} seconds of you speaking.")
        staged = MY_VOICE_DIR / "reference.wav.new"
        shutil.copyfile(sample, staged)
        os.replace(staged, MY_VOICE_FILE)
    return my_voice_status()


def forget_my_voice() -> dict:
    MY_VOICE_FILE.unlink(missing_ok=True)
    return my_voice_status()


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        return wav.getnframes() / rate if rate else 0.0


def voice_preview(text: str, voice: str, level: str) -> bytes:
    """A short playable copy of the reading, leveled the same way as the video mix."""
    spoken = speak(text, voice)
    target = VOICE_LEVELS.get(level, VOICE_LEVELS["normal"])
    exe = ffmpeg_path()
    if not exe:
        raise ValueError("ffmpeg is not installed, so the voice could not be prepared.")
    with tempfile.TemporaryDirectory(prefix="linkedin-voice-") as folder:
        root = Path(folder)
        (root / "speech.aiff").write_bytes(spoken)
        command = [
            exe, "-y", "-hide_banner", "-loglevel", "error",
            "-i", "speech.aiff",
            "-af", target,
            "-c:a", "aac",
            "-b:a", "128k",
            "-ac", "2",
            "preview.m4a",
        ]
        try:
            _run(command, 60, root)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError("The voice preview could not be made.") from exc
        data = (root / "preview.m4a").read_bytes() if (root / "preview.m4a").is_file() else b""
    if len(data) < 100 or b"ftyp" not in data[:32]:
        raise ValueError("The voice preview could not be made.")
    return data


def _speech_text(text: str) -> str:
    """The post as a voice would say it: no links, hashtags, or emoji, and a pause at each line break."""
    cleaned = re.sub(r"https?://\S+|www\.\S+", " ", str(text))
    cleaned = re.sub(r"#\w+", " ", cleaned)
    kept = []
    for character in cleaned:
        category = unicodedata.category(character)
        if character in "\n\t" or category[0] in "LNP" or character in " .,!?;:'’\"-()%&$":
            kept.append(character)
    lines = [" ".join(line.split()) for line in "".join(kept).splitlines()]
    lines = [line if line[-1:] in ".!?" else f"{line}." for line in lines if line]
    speech = " ".join(lines)[:4000].strip()
    if len(speech) < 2:
        raise ValueError("The post is too short to read aloud.")
    return speech


def join_videos(
    videos: list[bytes],
    music: str | None = None,
    level: str = "medium",
    voice: bytes | None = None,
    voice_level: str = "normal",
) -> bytes:
    """Play the card videos one after another. Names are ours; the request supplies only bytes."""
    slug = music if isinstance(music, str) and music in MUSIC_TRACKS else None
    gain = MUSIC_LEVELS.get(level, MUSIC_LEVELS["medium"])
    spoken = voice_level if voice_level in VOICE_LEVELS else "normal"
    if voice is not None and (len(voice) < 100 or len(voice) > MAX_VOICE_BYTES):
        raise ValueError("That recording is empty or too large.")
    if not videos:
        raise ValueError("There are no card videos to join.")
    if len(videos) > MAX_SCENE_VIDEOS:
        raise ValueError(f"Join {MAX_SCENE_VIDEOS} cards or fewer.")
    for video in videos:
        if len(video) < 1000 or len(video) > MAX_SCENE_VIDEO_BYTES or b"ftyp" not in video[:32]:
            raise ValueError("A card video was not a valid MP4.")
    if len(videos) == 1 and not slug and voice is None:
        return videos[0]
    if len(videos) == 1 and voice is None:
        return _with_bed(videos[0], slug, gain)
    if len(videos) == 1:
        return _with_voice(videos[0], slug, gain, voice, spoken)
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
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-map", "0:v:0", "-map", "1:a:0", "-shortest",
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "joined.mp4",
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
    if voice is not None:
        return _with_voice(data, slug, gain, voice, spoken)
    if slug:
        return _with_bed(data, slug, gain)
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


def _with_bed(video: bytes, slug: str, gain: float) -> bytes:
    """Replace the silent track with a bundled public-domain track, looped and kept quiet.

    The picture frames are copied, not re-encoded. The audio file is copied into the
    temp folder under a fixed name, so ffmpeg never sees a request path.
    """
    source = music_path(slug)
    exe = ffmpeg_path()
    if source is None:
        raise ValueError("The music could not be added to the video.")
    if not exe:
        raise ValueError("ffmpeg is not installed, so the music could not be added.")
    with tempfile.TemporaryDirectory(prefix="linkedin-bed-") as folder:
        root = Path(folder)
        (root / "video.mp4").write_bytes(video)
        (root / "bed.m4a").write_bytes(source.read_bytes())
        out = root / "with-bed.mp4"
        command = [
            exe, "-y", "-hide_banner", "-loglevel", "error",
            "-i", "video.mp4",
            "-stream_loop", "-1", "-i", "bed.m4a",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "96k",
            "-af", _quiet_fade(_media_duration(exe, root / "video.mp4"), gain),
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


def _media_duration(exe: str, path: Path) -> float:
    """Seconds from ffprobe. A bad reading falls back to a short fade window."""
    probe = str(Path(exe).with_name("ffprobe"))
    if not Path(probe).is_file():
        found = shutil.which("ffprobe")
        probe = found or ""
    if not probe:
        return 8.0
    try:
        completed = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path.name],
            check=True,
            timeout=30,
            capture_output=True,
            cwd=path.parent,
        )
        seconds = float(completed.stdout.decode().strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, OSError):
        return 8.0
    if not (0.4 <= seconds <= 600):
        return 8.0
    return seconds


def _with_voice(video: bytes, slug: str | None, gain: float, voice: bytes, voice_level: str) -> bytes:
    """Lay a voiceover on the video, and the music bed under it when one was chosen.

    The voice plays once and is padded with silence so a short recording does not cut the pictures.
    Audio bytes are written under fixed names. ffmpeg never sees a request path.
    """
    exe = ffmpeg_path()
    if not exe:
        raise ValueError("ffmpeg is not installed, so the voiceover could not be added.")
    source = music_path(slug) if slug else None
    if slug and source is None:
        raise ValueError("The music could not be added to the video.")
    voice_filter = VOICE_LEVELS.get(voice_level, VOICE_LEVELS["normal"])
    with tempfile.TemporaryDirectory(prefix="linkedin-voice-") as folder:
        root = Path(folder)
        (root / "video.mp4").write_bytes(video)
        (root / "voice.bin").write_bytes(voice)
        if source is not None:
            (root / "bed.m4a").write_bytes(source.read_bytes())
        seconds = _media_duration(exe, root / "video.mp4")
        # Music input is 1 when present; the voice input follows it. The music dips while the voice speaks.
        voice_index = 2 if source is not None else 1
        voice_chain = (
            f"[{voice_index}:a]{voice_filter},afade=t=in:st=0:d=0.12,"
            f"apad=whole_dur={seconds:.2f},atrim=0:{seconds:.2f},asetpts=PTS-STARTPTS"
        )
        if source is None:
            filter_complex = f"{voice_chain}[voice]"
            audio_map = "[voice]"
        else:
            filter_complex = ";".join([
                f"[1:a]{_quiet_fade(seconds, gain)},atrim=0:{seconds:.2f},asetpts=PTS-STARTPTS[music]",
                f"{voice_chain}[spoken]",
                "[spoken]asplit=2[key][speech]",
                "[music][key]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[ducked]",
                "[ducked][speech]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[mix]",
            ])
            audio_map = "[mix]"
        command = [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", "video.mp4"]
        if source is not None:
            command += ["-stream_loop", "-1", "-i", "bed.m4a"]
        command += [
            "-t", "180", "-i", "voice.bin",
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", audio_map,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "160k",
            "-t", f"{seconds:.2f}",
            "-movflags", "+faststart",
            "with-voice.mp4",
        ]
        try:
            _run(command, 120, root)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError(
                "The voiceover could not be added. Use an MP3, M4A, or WAV, or pick a Mac voice."
            ) from exc
        data = (root / "with-voice.mp4").read_bytes() if (root / "with-voice.mp4").is_file() else b""
    if len(data) < 1000 or b"ftyp" not in data[:32]:
        raise ValueError("The voiceover could not be added. Use an MP3, M4A, or WAV, or pick a Mac voice.")
    return data


def _quiet_fade(seconds: float, gain: float) -> str:
    """A chosen level with fades. The gain comes from MUSIC_LEVELS and the timing from the probed duration."""
    fade_in = min(1.2, max(0.2, seconds / 4))
    fade_out = min(1.5, max(0.3, seconds / 3))
    fade_at = max(0.0, seconds - fade_out)
    return (
        f"volume={gain:.3f},afade=t=in:st=0:d={fade_in:.2f},"
        f"afade=t=out:st={fade_at:.2f}:d={fade_out:.2f}"
    )


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
