"""Explainer storyboards stay inside the draft, and motion frames encode without Ollama."""

import re
import subprocess

import pytest

from cards import cards_from_draft
from media import ffmpeg_path, parse_fps, render_sequence
from motion import storyboard_from_deck, storyboard_from_plan, storyboard_from_script
from server import motion_from_multipart, script_plan

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
"""

BREACH = """How a breach reaches an internal api

The management plane was still reachable from the internet.

Egress left through a path with no inspection.

An attacker moved from the public edge to the internal api.

Would you close the public management plane first?
"""

BREACH_SHORT = """The management plane was still on the internet.

Egress left with no inspection.

An attacker reached the internal api.

Would you close the public management plane first?
"""


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def visible_text(board: dict) -> str:
    parts = [board["headline"], board["eyebrow"], *board["emphasis"]]
    for node in board["nodes"]:
        parts.append(node["label"])
    for beat in board["beats"]:
        parts.append(beat["caption"])
    return "\n".join(parts)


def test_storyboard_uses_only_draft_words() -> None:
    deck = cards_from_draft(ARTICLE, SHORT, ["agentic ops"], "")
    board = storyboard_from_deck(deck, ARTICLE, SHORT, ["agentic ops"])
    assert len(board["nodes"]) >= 3
    assert board["beats"]
    allowed = tokens(ARTICLE + SHORT + " agentic ops")
    assert tokens(visible_text(board)) <= allowed
    assert all(node["tone"] == "neutral" for node in board["nodes"])
    assert all(edge["tone"] == "neutral" for edge in board["edges"])


def test_breach_language_marks_the_last_path() -> None:
    deck = cards_from_draft(BREACH, BREACH_SHORT, ["cloud breach"], "")
    board = storyboard_from_deck(deck, BREACH, BREACH_SHORT, ["cloud breach"])
    side = [node for node in board["nodes"] if node["place"] == "side"]
    assert side and side[0]["tone"] == "alert"
    assert "attacker" in side[0]["label"].lower()
    side_beat = next(index for index, beat in enumerate(board["beats"]) if side[0]["id"] in beat["reveal"])
    assert any(edge["tone"] == "alert" and edge["beat"] == side_beat for edge in board["edges"])
    revealed = [node_id for beat in board["beats"] for node_id in beat["reveal"]]
    assert sorted(revealed) == sorted(node["id"] for node in board["nodes"])
    ids = {node["id"] for node in board["nodes"]}
    for edge in board["edges"]:
        assert edge["from"] in ids and edge["to"] in ids
    for word in board["emphasis"]:
        assert word in board["headline"].lower()


SCRIPT = """Agentic ops
How handoffs break the work

The model is rarely the part that fails.
A person still owns the decision.
Log every tool call.
Keep the source next to the claim.

What would you want a human to sign?
"""

PARAGRAPH = (
    "How handoffs break the work. The model is rarely the part that fails. "
    "A person still owns the decision. Log every tool call. "
    "What would you want a human to sign?"
)

ATTACK_SCRIPT = """How a breach crosses the public edge

The management plane stayed open.
Egress left without inspection.
An attacker reached the internal api.
Would you close that public path first?
"""


def test_script_uses_only_its_own_words() -> None:
    board, plan = storyboard_from_script(SCRIPT)
    assert plan["eyebrow"] == "Agentic ops"
    assert "handoffs" in plan["headline"].lower()
    assert len(plan["nodes"]) >= 3
    assert plan["nodes"][0]
    assert all(node["label"].split()[0].casefold() not in {"is", "are", "the"} for node in board["nodes"])
    assert any(line.endswith("?") for line in plan["captions"])
    assert board["nodes"][0]["place"] == "hub"
    assert board["nodes"][0]["label"] == plan["nodes"][0]
    allowed = tokens(SCRIPT)
    assert tokens(visible_text(board)) <= allowed
    revealed = [node_id for beat in board["beats"] for node_id in beat["reveal"]]
    assert sorted(revealed) == sorted(node["id"] for node in board["nodes"])


def test_paragraph_script_splits_into_boxes_and_a_question() -> None:
    board, plan = storyboard_from_script(PARAGRAPH)
    assert len(plan["nodes"]) >= 3
    assert any(line.endswith("?") for line in plan["captions"])
    assert tokens(visible_text(board)) <= tokens(PARAGRAPH)


def test_attack_line_sits_to_the_side() -> None:
    board, plan = storyboard_from_script(ATTACK_SCRIPT)
    side = [node for node in board["nodes"] if node["place"] == "side"]
    assert side and side[0]["tone"] == "alert"
    assert "attacker" in side[0]["label"].lower()
    assert plan["nodes"][0] == board["nodes"][0]["label"]
    assert board["nodes"][0]["place"] == "hub"


def test_edited_plan_replaces_the_words() -> None:
    board, plan = storyboard_from_plan(
        "How handoffs break the work",
        "Agentic ops",
        ["Owned decision", "Tool call log", "Source stays close"],
        ["Would you sign the handoff first?"],
    )
    text = visible_text(board)
    assert "Owned decision" in text
    assert "Would you sign the handoff first?" in text
    assert "rarely" not in text
    assert plan["nodes"] == ["Owned decision", "Tool call log", "Source stays close"]
    assert board["nodes"][0]["place"] == "hub"
    assert board["nodes"][0]["label"] == "Owned decision"


def test_thin_script_is_refused() -> None:
    with pytest.raises(ValueError, match="headline"):
        storyboard_from_script("Too thin")
    with pytest.raises(ValueError, match="three more lines"):
        storyboard_from_script("How handoffs break\nOnly two words here")
    with pytest.raises(ValueError, match="not valid"):
        storyboard_from_plan("How handoffs break", "", "Owned decision", [])


def test_script_plan_reads_a_script_and_an_edit() -> None:
    motion, plan = script_plan({"script": SCRIPT})
    assert motion["beats"]
    assert plan["eyebrow"] == "Agentic ops"
    edited, edited_plan = script_plan({
        "headline": "How handoffs break the work",
        "nodes": ["Owned decision", "Tool call log", "Source stays close"],
        "captions": ["Would you sign the handoff first?"],
    })
    assert "Owned decision" in visible_text(edited)
    assert edited_plan["captions"] == ["Would you sign the handoff first?"]
    with pytest.raises(ValueError, match="not valid"):
        script_plan(["nope"])


def test_thin_draft_skips_the_diagram() -> None:
    board = storyboard_from_deck({"slides": []}, "", "", [])
    assert board["nodes"] == []
    assert board["beats"] == []


def test_parse_fps_rejects_a_command() -> None:
    assert parse_fps("10") == 10
    with pytest.raises(ValueError):
        parse_fps("10; rm")
    with pytest.raises(ValueError):
        parse_fps("30")


def test_motion_multipart_orders_frames_without_using_the_filename_as_a_path() -> None:
    boundary = "----bound"
    chunks = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="fps"\r\n\r\n8\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="frames"; filename="frame-002.jpg"\r\n\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="frames"; filename="../../frame-001.jpg"\r\n\r\n',
        f'--{boundary}--\r\n',
    ]
    body = chunks[0].encode() + chunks[1].encode() + b"second" + b"\r\n" + chunks[2].encode() + b"first" + b"\r\n" + chunks[3].encode()
    frames, fps = motion_from_multipart(f'multipart/form-data; boundary="{boundary}"', body)
    assert fps == 8
    assert frames == [b"first", b"second"]


def test_render_sequence_when_ffmpeg_is_installed() -> None:
    exe = ffmpeg_path()
    if not exe:
        pytest.skip("ffmpeg is not installed")
    frames = []
    for color in ("0x071422", "0x102c44"):
        for _ in range(4):
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
                    f"color=c={color}:s=160x200",
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
    video = render_sequence(frames, 8)
    assert b"ftyp" in video[:32]
    probed = subprocess.run(
        [exe.replace("ffmpeg", "ffprobe") if exe.endswith("ffmpeg") else "ffprobe",
         "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "-"],
        input=video,
        check=True,
        timeout=30,
        capture_output=True,
    )
    duration = float(probed.stdout.strip() or "0")
    assert 0.7 <= duration <= 1.4
