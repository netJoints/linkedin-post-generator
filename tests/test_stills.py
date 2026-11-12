"""Picture videos accept bounded JPEGs and a caption overlay, and ffmpeg builds the MP4."""

import subprocess

import pytest

from media import ffmpeg_path
from stills import MAX_STILLS, check_overlay, check_still, render_stills, stills_from_multipart


def _jpeg(color: str = "0x123456") -> bytes:
    exe = ffmpeg_path()
    assert exe
    completed = subprocess.run(
        [
            exe, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=640x800",
            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
        ],
        check=True,
        timeout=30,
        capture_output=True,
    )
    return completed.stdout


def _png() -> bytes:
    exe = ffmpeg_path()
    assert exe
    completed = subprocess.run(
        [
            exe, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black@0.0:s=1080x1350,format=rgba",
            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1",
        ],
        check=True,
        timeout=30,
        capture_output=True,
    )
    return completed.stdout


def _part(name: str, content: bytes) -> bytes:
    header = (
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    return header + content


def _body(parts: list[tuple[str, bytes]]) -> tuple[str, bytes]:
    boundary = "----stills-test"
    chunks = [b"--" + boundary.encode()]
    for name, content in parts:
        chunks.append(_part(name, content))
        chunks.append(b"--" + boundary.encode())
    chunks[-1] += b"--\r\n"
    return f"multipart/form-data; boundary={boundary}", b"\r\n".join(chunks)


def test_a_caption_follows_its_picture_number_not_the_upload_order() -> None:
    if not ffmpeg_path():
        pytest.skip("ffmpeg is not installed")
    first = _jpeg("0x112233")
    second = _jpeg("0x334455")
    content_type, body = _body(
        [
            ("caption-02.png", _png()),
            ("still-02.jpg", second),
            ("still-01.jpg", first),
        ]
    )
    shots = stills_from_multipart(content_type, body)
    assert len(shots) == 2
    assert shots[0][0] == first
    assert shots[0][1] is None
    assert shots[1][0] == second
    assert shots[1][1] is not None


def test_a_picture_must_be_a_jpeg_and_a_caption_must_be_the_video_size() -> None:
    with pytest.raises(ValueError):
        check_still(b"\x89PNG" + b"\x00" * 120)
    with pytest.raises(ValueError):
        check_still(b"\xff\xd8\xff" + b"\x00" * 200)
    overlay = b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + (1).to_bytes(4, "big") + (1).to_bytes(4, "big")
    with pytest.raises(ValueError):
        check_overlay(overlay)
    content_type, body = _body([("notes.txt", b"hello")])
    with pytest.raises(ValueError):
        stills_from_multipart(content_type, body)


def test_too_many_pictures_are_refused() -> None:
    if not ffmpeg_path():
        pytest.skip("ffmpeg is not installed")
    picture = _jpeg()
    parts = [(f"still-{index:02d}.jpg", picture) for index in range(1, MAX_STILLS + 2)]
    content_type, body = _body(parts)
    with pytest.raises(ValueError, match="12"):
        stills_from_multipart(content_type, body)


def test_render_stills_when_ffmpeg_is_installed() -> None:
    exe = ffmpeg_path()
    if not exe:
        pytest.skip("ffmpeg is not installed")
    video = render_stills([(_jpeg("0x071422"), None), (_jpeg("0xf3f6fa"), _png())])
    assert b"ftyp" in video[:32]
    probe = subprocess.run(
        [
            exe.replace("ffmpeg", "ffprobe") if exe.endswith("ffmpeg") else "ffprobe",
            "-v", "error",
            "-show_entries", "stream=codec_name,width,height,pix_fmt",
            "-show_entries", "format=duration",
            "-of", "default=nw=1",
            "-i", "pipe:0",
        ],
        input=video,
        check=True,
        timeout=30,
        capture_output=True,
    )
    text = probe.stdout.decode()
    assert "codec_name=h264" in text
    assert "width=1080" in text
    assert "height=1350" in text
    assert "pix_fmt=yuv420p" in text
    duration = next(float(line.split("=", 1)[1]) for line in text.splitlines() if line.startswith("duration="))
    assert duration == pytest.approx(6.8, abs=0.15)
