"""Checks that do not need Ollama or the network."""

import pytest

from server import validate_public_url
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


def test_local_addresses_are_blocked() -> None:
    with pytest.raises(ValueError):
        validate_public_url("http://127.0.0.1/secret")
    with pytest.raises(ValueError):
        validate_public_url("http://localhost/secret")
