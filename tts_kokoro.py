"""Read text aloud with Kokoro-82M, an Apache 2.0 model that runs on this laptop.

The app runs this file with its own Python, so the app itself keeps no third-party packages.
Input: JSON on stdin, {"text": str, "voice": str}. The voice must be on VOICES.
Output: a WAV file on stdout. Nothing is read from or written to a path the request chooses.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HOME = Path.home() / ".linkedin-tts"
MODEL = HOME / "kokoro-v1.0.onnx"
VOICE_FILE = HOME / "voices-v1.0.bin"
RATE = 24000
PAUSE_SECONDS = 0.35
MAX_CHARS = 4000
VOICES = {
    "af_heart": "en-us",
    "af_bella": "en-us",
    "af_nicole": "en-us",
    "am_michael": "en-us",
    "bf_emma": "en-gb",
    "bm_george": "en-gb",
}


def chunks(text: str) -> list[str]:
    """Sentences grouped into pieces under Kokoro's comfortable length."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    grouped: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > 300:
            grouped.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        grouped.append(current)
    return grouped


def main() -> None:
    payload = json.loads(sys.stdin.read())
    text = str(payload.get("text", ""))[:MAX_CHARS].strip()
    voice = payload.get("voice")
    if voice not in VOICES or len(text) < 2:
        raise SystemExit("Choose a voice from the list and write some text.")
    if not MODEL.is_file() or not VOICE_FILE.is_file():
        raise SystemExit("The AI voice files are missing. See the setup note.")
    model = Kokoro(str(MODEL), str(VOICE_FILE))
    pause = np.zeros(int(RATE * PAUSE_SECONDS), dtype=np.float32)
    pieces = []
    for part in chunks(text):
        samples, rate = model.create(part, voice=voice, speed=1.0, lang=VOICES[voice])
        if rate != RATE:
            raise SystemExit("The voice used an unexpected sample rate.")
        pieces.append(np.asarray(samples, dtype=np.float32))
        pieces.append(pause)
    if not pieces:
        raise SystemExit("There was nothing to read.")
    sf.write(sys.stdout.buffer, np.concatenate(pieces[:-1]), RATE, format="WAV", subtype="PCM_16")


if __name__ == "__main__":
    main()
