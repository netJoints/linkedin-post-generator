#!/usr/bin/env python3
"""Chatterbox text-to-speech for the picture videos (MIT, Resemble AI).

Runs with the Chatterbox virtual environment, not the app's own Python:
    python tts_chatterbox.py default
    python tts_chatterbox.py clone /path/to/reference.wav

Input on stdin: JSON {"text": "..."}. Output on stdout: a 16-bit mono WAV.
The model comes from the Hugging Face cache. Offline mode is forced, so nothing is
downloaded while a video is being made. The reference path is a file the app wrote
into its own temp folder. Nothing from the request is used as a path.
"""

import io
import json
import os
import re
import sys
import wave
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

MAX_CHARS = 4000
CHUNK_CHARS = 250
PAUSE_SECONDS = 0.35


def chunks(text: str) -> list[str]:
    """Group whole sentences into pieces of about CHUNK_CHARS. Long pieces make the model drift."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + 1 + len(sentence) > CHUNK_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def main() -> None:
    # Keep the WAV on the real stdout. The model prints load messages, so send those to stderr.
    out = sys.stdout.buffer
    sys.stdout = sys.stderr

    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in {"default", "clone"}:
        raise SystemExit("Mode must be default or clone.")
    reference = None
    if mode == "clone":
        if len(sys.argv) < 3 or not Path(sys.argv[2]).is_file():
            raise SystemExit("Clone mode needs a reference recording.")
        reference = sys.argv[2]

    request = json.loads(sys.stdin.read() or "{}")
    text = request.get("text", "") if isinstance(request, dict) else ""
    if not isinstance(text, str) or len(text.strip()) < 2:
        raise SystemExit("The text is too short.")
    text = text[:MAX_CHARS]

    import torch
    import numpy as np
    from chatterbox.tts import ChatterboxTTS

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = ChatterboxTTS.from_pretrained(device=device)
    if reference:
        model.prepare_conditionals(reference, exaggeration=0.5)

    gap = torch.zeros(1, int(model.sr * PAUSE_SECONDS))
    pieces = []
    with torch.inference_mode():
        for index, part in enumerate(chunks(text)):
            if index:
                pieces.append(gap)
            pieces.append(model.generate(part).cpu())
    audio = torch.cat(pieces, dim=-1).squeeze(0)
    pcm = (audio.clamp(-1, 1) * 32767).to(torch.int16).numpy().astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(model.sr)
        wav.writeframes(pcm.tobytes())
    out.write(buffer.getvalue())
    out.flush()


if __name__ == "__main__":
    main()
