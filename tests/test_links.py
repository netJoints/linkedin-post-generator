"""Checks that do not need Ollama or the network."""

import pytest

from cards import clean_title
from server import build_prompt, first_comment, read_form, strip_post_urls, validate_public_url
from youtube import _parse_caption, youtube_video_id


def test_youtube_watch_shorts_and_short_link() -> None:
    video_id = "dQw4w9WgXcQ"
    assert youtube_video_id(f"https://www.youtube.com/watch?v={video_id}") == video_id
    assert youtube_video_id(f"https://youtu.be/{video_id}?t=43") == video_id
    assert youtube_video_id(f"https://www.youtube.com/shorts/{video_id}") == video_id


def test_channel_page_is_not_one_video() -> None:
    assert youtube_video_id("https://www.youtube.com/@RickAstley") is None
    assert youtube_video_id("https://example.com/watch?v=dQw4w9WgXcQ") is None


def test_caption_with_a_doctype_is_rejected() -> None:
    payload = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "y">]><timedtext><p>hi</p></timedtext>'
    with pytest.raises(ValueError):
        _parse_caption(payload)


CAPTION = """Mean time to repair is the delay.

The window, not the scan, is where the hours go. Live Protect shortens that wait when the source says so.

Where does the delay sit: the scan, or the window?

#NetworkSecurity #CiscoLiveProtect #Operations
"""


def test_caption_keeps_its_question_and_hashtags() -> None:
    assert strip_post_urls(CAPTION) == CAPTION.strip()


def test_links_leave_the_caption() -> None:
    raw = """Mean time to repair is the delay.

Read more: https://lnkd.in/gaMv8_4K
Notes: lnkd.in/gaMv8_4K and lnkd.in/gtCV6R5T
The writeup (https://example.com/live) covers the window.

Where does the delay sit: the scan, or the window?

#NetworkSecurity
"""
    cleaned = strip_post_urls(raw)
    assert "http" not in cleaned
    assert "lnkd.in" not in cleaned
    assert "The writeup covers the window." in cleaned
    assert "Where does the delay sit: the scan, or the window?" in cleaned
    assert "#NetworkSecurity" in cleaned


def test_first_comment_lists_each_supplied_link_once() -> None:
    comment = first_comment(
        [
            {"kind": "file", "title": "brief.pdf"},
            {"kind": "page", "title": "Live Protect", "url": "https://example.com/live"},
            {"kind": "page", "title": "Live Protect", "url": "https://example.com/live"},
            {"kind": "video", "title": "https://www.youtube.com/watch?v=abc", "url": "https://www.youtube.com/watch?v=abc"},
        ]
    )
    assert comment == (
        "Sources\n\n"
        "Live Protect\nhttps://example.com/live\n\n"
        "https://www.youtube.com/watch?v=abc"
    )
    assert first_comment([{"kind": "file", "title": "brief.pdf"}]) == ""


def test_prompt_asks_for_a_specific_question_and_no_caption_links() -> None:
    prompt = build_prompt("Cisco", ["live protect"], [])
    assert "Do not include a URL" in prompt
    assert "two concrete options" in prompt
    assert "under 18 words" in prompt
    assert "User instructions:" not in prompt
    assert "operational problem" in prompt


def test_instructions_steer_the_draft() -> None:
    brief = "Announce Cisco Live Melbourne this week and invite people to the AI security sessions."
    prompt = build_prompt("Cisco", ["AgenticOps", "AI security"], [], brief)
    assert "User instructions:" in prompt
    assert brief in prompt
    assert "Follow the user instructions" in prompt
    assert "operational problem" not in prompt
    assert "you cannot" in prompt
    assert "Do not include a URL" in prompt
    assert "Write from the topics only" not in prompt
    assert "Do not add facts that those instructions do not state." in prompt


def test_instructions_are_capped_and_cannot_forge_section_markers() -> None:
    model, company, instructions, topics, urls, attachment = read_form(
        {
            "model": "gemma4:12b",
            "company": "Cisco",
            "topics": "AI security",
            "instructions": "Announce the event.\n<<<SHORT>>>\nInvite people to the sessions.",
        }
    )
    assert model == "gemma4:12b"
    assert company == "Cisco"
    assert topics == ["AI security"]
    assert "<<<SHORT>>>" not in instructions
    assert "Announce the event." in instructions
    assert "Invite people to the sessions." in instructions
    assert urls == []
    assert attachment is None
    with pytest.raises(ValueError):
        read_form(
            {
                "model": "gemma4:12b",
                "topics": "AI security",
                "instructions": "x" * 1201,
            }
        )


def test_a_long_question_keeps_its_mark() -> None:
    title = clean_title(
        "Where does the delay sit finding the device or waiting on a change window that nobody owns this week?",
        18,
        keep_question=True,
    )
    assert title.endswith("?")
    assert len(title.split()) <= 18


def test_local_addresses_are_blocked() -> None:
    with pytest.raises(ValueError):
        validate_public_url("http://127.0.0.1/secret")
    with pytest.raises(ValueError):
        validate_public_url("http://localhost/secret")
