from __future__ import annotations

import re
import subprocess

import pytest

from media import ffmpeg_path, join_videos, render_sequence
from motion import MAX_SCENES, SCENE_SECONDS, scenes_from_payload, storyboard_from_scene
from server import videos_from_multipart

PROSE = """Human-only NetOps can no longer keep pace with the complexity and speed of modern digital environments.

Enterprises will not trust critical infrastructure to black-box autonomy.

That is why Cisco AgenticOps is built around a different principle: autonomy must earn trust every time it acts."""

DIAGRAM = """Agentic ops
How handoffs break the work

The model is rarely the part that fails.
A person still owns the decision.
Log every tool call.
Keep the source next to the claim.

What would you want a human to sign?"""

SCRIPTS = {
    "compare": PROSE,
    "statement": "Autonomy must earn trust every time it acts.",
    "question": "Where does the delay sit: the scan, or the change window?",
    "steps": "How an agent closes a ticket\n1. It reads the alert and the topology.\n2. It proposes a fix with the evidence.\n3. A person approves the change.",
    "checklist": "Before you ship an agent:\nLog every tool call.\nScope its permissions.\nKeep a human on approvals.\nTest the rollback.",
    "diagram": DIAGRAM,
}


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def visible_text(board: dict) -> str:
    parts = [board["headline"], board["eyebrow"], *board["emphasis"], *board["columns"]]
    parts.extend(node["label"] for node in board["nodes"])
    parts.extend(beat["caption"] for beat in board["beats"])
    return "\n".join(parts)


def length(board: dict) -> float:
    return len(board["beats"]) * board["seconds"] + board["tail"]


@pytest.mark.parametrize("layout", sorted(SCRIPTS))
def test_auto_picks_the_layout_from_the_script(layout: str) -> None:
    board, plan = storyboard_from_scene(SCRIPTS[layout])
    assert plan["layout"] == layout
    assert board["layout"] == layout
    assert plan["note"] == ""


@pytest.mark.parametrize("layout", sorted(SCRIPTS))
def test_every_card_lasts_eleven_seconds_and_uses_only_its_words(layout: str) -> None:
    script = SCRIPTS[layout]
    board, _ = storyboard_from_scene(script)
    assert length(board) == pytest.approx(SCENE_SECONDS, abs=0.01)
    assert board["tail"] > 0
    assert tokens(visible_text(board)) <= tokens(script)


def test_prose_compares_the_problem_with_the_principle() -> None:
    board, _ = storyboard_from_scene(PROSE)
    left = [node["label"] for node in board["nodes"] if node["place"] == "left"]
    right = [node["label"] for node in board["nodes"] if node["place"] == "right"]
    assert len(left) == 2 and left[1].startswith("Enterprises will not trust")
    assert right == ["Cisco AgenticOps is built around a different principle", "Autonomy must earn trust every time it acts"]


def test_before_and_after_prefixes_become_column_headers() -> None:
    board, _ = storyboard_from_scene("Before: Tickets wait for a change window.\nAfter: Fixes ship with evidence attached.")
    assert board["layout"] == "compare"
    assert board["columns"] == ["Before", "After"]


def test_question_lists_both_choices() -> None:
    board, _ = storyboard_from_scene(SCRIPTS["question"])
    assert [node["label"] for node in board["nodes"]] == ["The scan", "The change window"]


def test_chosen_layout_is_used_when_it_fits() -> None:
    _, plan = storyboard_from_scene(SCRIPTS["checklist"], "steps")
    assert plan["layout"] == "steps"
    assert plan["note"] == ""


def test_a_layout_that_does_not_fit_falls_back_with_a_note() -> None:
    board, plan = storyboard_from_scene(SCRIPTS["statement"], "diagram")
    assert plan["layout"] == "statement"
    assert "Diagram needs more lines" in plan["note"]
    assert length(board) == pytest.approx(SCENE_SECONDS, abs=0.01)


def test_six_cards_make_about_sixty_six_seconds() -> None:
    payload = {"scenes": [{"script": script, "layout": "auto"} for script in SCRIPTS.values()]}
    scenes = scenes_from_payload(payload)
    assert [scene["card"] for scene in scenes] == [1, 2, 3, 4, 5, 6]
    assert all("motion" in scene for scene in scenes)
    assert sum(length(scene["motion"]) for scene in scenes) == pytest.approx(66, abs=0.05)
    assert [scene["motion"]["position"] for scene in scenes] == [1, 2, 3, 4, 5, 6]
    assert {scene["motion"]["count"] for scene in scenes} == {6}


def test_empty_cards_are_skipped_and_a_bad_card_reports_its_error() -> None:
    payload = {"scenes": [{"script": ""}, {"script": "Too short"}, {"script": SCRIPTS["statement"]}]}
    scenes = scenes_from_payload(payload)
    assert scenes[0] == {"card": 2, "error": scenes[0]["error"]}
    assert scenes[1]["card"] == 3 and scenes[1]["motion"]["count"] == 2


def test_payload_limits() -> None:
    with pytest.raises(ValueError, match="at least one card"):
        scenes_from_payload({"scenes": [{"script": "  "}]})
    with pytest.raises(ValueError, match="cards or fewer"):
        scenes_from_payload({"scenes": [{"script": "x"}] * (MAX_SCENES + 1)})
    with pytest.raises(ValueError, match="longer than"):
        scenes_from_payload({"scenes": [{"script": "word " * 400}]})
    with pytest.raises(ValueError):
        scenes_from_payload({"scenes": "not a list"})


def test_stitch_multipart_orders_videos_by_card() -> None:
    boundary = "----bound"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="videos"; filename="scene-02.mp4"\r\n\r\n'.encode()
        + b"second\r\n"
        + f'--{boundary}\r\nContent-Disposition: form-data; name="videos"; filename="../scene-01.mp4"\r\n\r\n'.encode()
        + b"first\r\n"
        + f"--{boundary}--\r\n".encode()
    )
    videos = videos_from_multipart(f'multipart/form-data; boundary="{boundary}"', body)
    assert videos[-1] == b"second"


def test_join_rejects_files_that_are_not_mp4() -> None:
    with pytest.raises(ValueError):
        join_videos([b"x" * 2000, b"y" * 2000])


def _clip(exe: str, color: str) -> bytes:
    frames = []
    for _ in range(8):
        completed = subprocess.run(
            [exe, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=160x200",
             "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
            check=True,
            timeout=30,
            capture_output=True,
        )
        frames.append(completed.stdout)
    return render_sequence(frames, 8)


def test_join_videos_when_ffmpeg_is_installed() -> None:
    exe = ffmpeg_path()
    if not exe:
        pytest.skip("ffmpeg is not installed")
    video = join_videos([_clip(exe, "0x071422"), _clip(exe, "0x102c44")])
    assert b"ftyp" in video[:32]
    probe = exe.replace("ffmpeg", "ffprobe") if exe.endswith("ffmpeg") else "ffprobe"
    probed = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "-"],
        input=video,
        check=True,
        timeout=30,
        capture_output=True,
    )
    assert 1.7 <= float(probed.stdout.strip() or "0") <= 2.6
