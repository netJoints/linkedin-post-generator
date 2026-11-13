"""Turn pictures into one LinkedIn post with the local vision model.

The pictures are not saved. Their bytes go to Ollama on this laptop and are then discarded.
File names from the browser are never used as paths.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request

MAX_PICTURES = 10
MAX_PICTURE_BYTES = 3_000_000
JPEG_PREFIX = b"\xff\xd8\xff"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
_FENCE = re.compile(r"^```[a-z]*\s*|\s*```$", re.I)
_LABEL = re.compile(r"^(?:linkedin post|post|caption)\s*:\s*", re.I)
_THINK = re.compile(r"<think>.*?</think>", re.I | re.S)


def check_jpeg(data: bytes) -> None:
    """Accept only a JPEG the page drew. The browser's file type is not trusted."""
    if len(data) < 100 or len(data) > MAX_PICTURE_BYTES or not data.startswith(JPEG_PREFIX):
        raise ValueError("One picture could not be read. Use a JPEG, PNG, WEBP, GIF, or SVG.")


def picture_prompt(instructions: str, count: int) -> str:
    brief = instructions.strip()
    asked = f"The writer asked for this:\n{brief}\n\n" if brief else ""
    noun = "picture" if count == 1 else "pictures"
    return (
        f"You are looking at {count} {noun}, in the order they were uploaded. "
        "Write one LinkedIn post a person could publish from them.\n\n"
        f"{asked}"
        "Rules:\n"
        "- Use only what is visible in the pictures, plus the request above.\n"
        "- Do not invent numbers, names, products, dates, or events.\n"
        "- Do not include a URL.\n"
        "- Plain text. No title line, no section labels, no markdown.\n"
        "- About 80 to 160 words. Open with the point. End with one specific question.\n"
        "- Add up to three hashtags only when the subject is clear from the pictures.\n"
    )


def vision_payload(model: str, prompt: str, images: list[bytes]) -> dict:
    payload: dict = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(image).decode("ascii") for image in images],
            }
        ],
        # Picture reads run past the 8192 draft context: one set of slides measured 9103 tokens.
        # 12288 leaves room for the reply and stays within this laptop's video memory.
        "options": {"temperature": 0.4, "num_predict": 700, "num_ctx": 12288},
        "keep_alive": "10m",
    }
    if model.startswith("gemma"):
        payload["think"] = False
    return payload


def finish_post(text: str) -> str:
    cleaned = _THINK.sub("", str(text or ""))
    cleaned = _FENCE.sub("", cleaned).strip()
    cleaned = _LABEL.sub("", cleaned).strip()
    cleaned = cleaned.replace("\x00", "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned.split()) < 20:
        raise ValueError(
            "The model could not write a post from these pictures. Add a short instruction, or try fewer pictures."
        )
    return cleaned[:4000]


def post_from_pictures(model: str, instructions: str, images: list[bytes]) -> str:
    if not images:
        raise ValueError("Add at least one picture.")
    if len(images) > MAX_PICTURES:
        raise ValueError(f"Use {MAX_PICTURES} pictures or fewer.")
    for image in images:
        check_jpeg(image)
    payload = vision_payload(model, picture_prompt(instructions, len(images)), images)
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            event = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").lower()
        if "context" in detail:
            raise ValueError(
                "These pictures are too much for the model in one go. Remove a few and read them again."
            ) from exc
        raise ValueError(
            "The model could not read these pictures. Try fewer pictures, or the other model."
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ValueError("Ollama is not running, so the pictures could not be read.") from exc
    if event.get("error"):
        raise ValueError("The model could not read these pictures. Try fewer pictures, or the other model.")
    return finish_post(str(event.get("message", {}).get("content") or ""))
