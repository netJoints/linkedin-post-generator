"""Card copy stays inside the draft, and video frames are checked without Ollama."""

import json
import re
import subprocess

import pytest

from cards import cards_from_draft, cards_from_model, design_cards
from media import ffmpeg_path, render_mp4, validate_frames

ARTICLE = """How handoffs break agentic ops

The model is rarely the part that fails. The handoff is.

A person still has to own the decision the system is not allowed to make. Write that decision down before you add another tool.

Log the tool call with its inputs and its result. A vibe check does not tell you what the agent did.

Keep the source next to the claim. If the page did not say it, the draft should not say it.

What would you want a human to sign?
"""

SHORT = """Agentic ops fails in the handoff.

The model is rarely the part that fails. Name the decision a person still owns.

What would you want a human to sign?

#agentic #operations
"""

SOURCE = ARTICLE + "\n" + SHORT


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def slide_text(deck: dict) -> str:
    parts = []
    for slide in deck["slides"]:
        parts.append(slide.get("title", ""))
        parts.append(slide.get("body", ""))
        parts.extend(slide.get("items", []))
    return "\n".join(parts)


def test_fallback_builds_a_deck_from_the_draft() -> None:
    deck = cards_from_draft(ARTICLE, SHORT, ["agentic ops"], "Cisco")
    kinds = [slide["kind"] for slide in deck["slides"]]
    assert kinds[0] == "hook"
    assert "point" in kinds
    assert "checklist" in kinds
    assert kinds[-1] == "close"
    assert deck["slides"][0]["title"] == "Agentic ops fails in the handoff"
    assert deck["slides"][-1]["title"].endswith("?")
    assert deck["footer"] == "Cisco"
    assert deck["eyebrow"] == "agentic ops"
    assert "#" not in slide_text(deck)


def test_fallback_does_not_add_words() -> None:
    deck = cards_from_draft(ARTICLE, SHORT, ["agentic ops"], "")
    allowed = tokens(SOURCE + " agentic ops in short")
    assert tokens(slide_text(deck)) <= allowed
    assert deck["footer"] == ""


def test_empty_draft_skips_the_model() -> None:
    called = False

    def complete(system: str, prompt: str) -> str:
        nonlocal called
        called = True
        return "{}"

    deck = design_cards("  ", "", [], "", complete)
    assert called is False
    assert deck["slides"] == []


def test_unusable_model_reply_falls_back_to_the_draft() -> None:
    deck = design_cards(ARTICLE, SHORT, ["agentic ops"], "", lambda system, prompt: "nope")
    assert deck["slides"][0]["title"] == "Agentic ops fails in the handoff"


def test_model_cards_are_reordered_and_keep_the_question() -> None:
    raw = json.dumps(
        {
            "eyebrow": "Agentic ops",
            "slides": [
                {"kind": "close", "title": "Ignore this close", "body": ""},
                {"kind": "point", "title": "Name the decision a person still owns", "body": "Write that decision down."},
                {"kind": "hook", "title": "Agentic ops fails in the handoff", "body": ""},
                {"kind": "point", "title": "Log the tool call and its result", "body": ""},
                {"kind": "checklist", "title": "Keep", "items": ["Name the decision", "Log the tool call"]},
                {"kind": "point", "title": "Keep the source next to the claim", "body": ""},
            ],
        }
    )
    deck = cards_from_model(raw, ARTICLE, SHORT, ["agentic ops"], "")
    assert deck is not None
    assert [slide["kind"] for slide in deck["slides"][:1]] == ["hook"]
    assert deck["slides"][-1]["kind"] == "close"
    assert deck["slides"][-1]["title"] == "What would you want a human to sign?"


def test_a_new_statistic_discards_the_model_deck() -> None:
    raw = json.dumps(
        {
            "eyebrow": "Agentic ops",
            "slides": [
                {"kind": "hook", "title": "Agentic ops fails in the handoff", "body": ""},
                {"kind": "point", "title": "Name the decision a person still owns", "body": ""},
                {"kind": "point", "title": "This raises output 14 percent", "body": "Teams move faster afterward."},
                {"kind": "close", "title": "What would you want a human to sign?", "body": ""},
            ],
        }
    )
    assert cards_from_model(raw, ARTICLE, SHORT, ["agentic ops"], "") is None


def test_hashtags_urls_and_markers_are_stripped() -> None:
    raw = json.dumps(
        {
            "eyebrow": "Agentic ops",
            "slides": [
                {"kind": "hook", "title": "Agentic ops fails in the handoff #ops", "body": ""},
                {"kind": "point", "title": "Read https://example.com/secret today", "body": "Use <<<ARTICLE>>> carefully here."},
                {"kind": "point", "title": "Log the tool call and its result", "body": ""},
                {"kind": "close", "title": "What would you want a human to sign?", "body": ""},
            ],
        }
    )
    deck = cards_from_model(raw, ARTICLE, SHORT, ["agentic ops"], "")
    assert deck is not None
    text = slide_text(deck)
    assert "#" not in text
    assert "http" not in text
    assert "ARTICLE" not in text


def test_video_frames_must_be_jpeg_and_bounded() -> None:
    with pytest.raises(ValueError):
        validate_frames([])
    with pytest.raises(ValueError):
        validate_frames([b"\x89PNG" + b"\x00" * 120])
    with pytest.raises(ValueError):
        validate_frames([b"\xff\xd8\xff" + b"\x00" * 20])
    validate_frames([b"\xff\xd8\xff" + b"\x00" * 120])


def test_render_mp4_when_ffmpeg_is_installed() -> None:
    exe = ffmpeg_path()
    if not exe:
        pytest.skip("ffmpeg is not installed")
    frames = []
    for color in ("0x071422", "0xf3f6fa"):
        completed = subprocess.run(
            [
                exe,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=640x800",
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
            ],
            check=True,
            timeout=30,
            capture_output=True,
        )
        frames.append(completed.stdout)
    video = render_mp4(frames)
    assert b"ftyp" in video[:32]
    assert len(video) > 1000
