#!/usr/bin/env python3
"""Local LinkedIn draft generator. Talks only to Ollama on this machine."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_URLS = 5
MAX_BYTES = 500_000
FETCH_TIMEOUT = 12
TEXT_LIMIT = 4_000

MODELS = (
    {
        "id": "mistral-small3.2",
        "label": "Mistral Small 3.2 (24B)",
    },
    {
        "id": "gemma4:12b",
        "label": "Gemma 4 12B",
    },
)
MODEL_IDS = {model["id"] for model in MODELS}

ARTICLE_MARK = "<<<ARTICLE>>>"
SHORT_MARK = "<<<SHORT>>>"

SYSTEM_PROMPT = """You write LinkedIn articles and the shorter feed post that goes with them.
Rules:
- Use only the company, topics, and source excerpts given to you. Do not invent statistics, quotes, customers, product capabilities, or personal anecdotes.
- If the sources do not support a claim, leave it out.
- Write plain text that can be pasted into LinkedIn. No markdown, no HTML, no asterisks.
- Sound like a practitioner. Do not use filler such as "in today's rapidly evolving landscape", "delve", "leverage", "game-changer", or "I'm excited to share".
- Do not assign yourself a job title, and do not write as an official company spokesperson.
- Mention the company only when one was provided. Do not claim what that company built, sold, or announced unless a source excerpt says so.
"""


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._capture: str | None = None
        self._buf: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False
        self.description = ""
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = True
        attr = {key.lower(): (value or "") for key, value in attrs}
        key = attr.get("name", "").lower() or attr.get("property", "").lower()
        if tag == "meta" and key in {"description", "og:description"} and not self.description:
            self.description = attr.get("content", "").strip()
        if tag in {"p", "h1", "h2", "h3", "li"}:
            self._capture = tag
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe"} and self._skip:
            self._skip -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag == self._capture:
            text = clean_space(" ".join(self._buf))
            if text:
                self.blocks.append(text)
            self._capture = None
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._capture:
            self._buf.append(data)


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_lines(value: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[\n,]+", value):
        item = clean_space(chunk)
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            items.append(item)
    return items


def validate_public_url(raw: str) -> str:
    url = raw.strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Use an http or https link.")
    if parsed.username or parsed.password:
        raise ValueError("Remove any username or password from the link.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "0.0.0.0"} or host.endswith(".localhost"):
        raise ValueError("Local addresses are blocked.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve {host}.") from exc
    for info in addresses:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise ValueError("That address is blocked.")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_url(url: str) -> dict[str, str]:
    """Fetch a page and return title, description, and readable text."""
    opener = urllib.request.build_opener(_NoRedirect)
    current = validate_public_url(url)
    body = b""
    content_type = ""
    for _ in range(5):
        request = urllib.request.Request(
            current,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; LocalDraft/1.0)",
                "Accept": "text/html,application/json;q=0.9,text/plain;q=0.8",
            },
        )
        try:
            response = opener.open(request, timeout=FETCH_TIMEOUT)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"The site returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Could not open the link ({exc.reason}).") from exc
        status = getattr(response, "status", 200)
        if status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("The site redirected without a destination.")
            current = validate_public_url(urllib.parse.urljoin(current, location))
            continue
        with response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_BYTES + 1)
            current = response.geturl()
        validate_public_url(current)
        break
    else:
        raise ValueError("That link redirected too many times.")
    if len(body) > MAX_BYTES:
        body = body[:MAX_BYTES]
    lowered = content_type.lower()
    if "html" not in lowered and "text" not in lowered and "json" not in lowered and lowered:
        raise ValueError("That link is not a readable page.")
    charset = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, re.I)
    if match:
        charset = match.group(1)
    html = body.decode(charset, errors="replace")
    parser = PageText()
    parser.feed(html)
    title = clean_space(" ".join(parser.title_parts))
    text = "\n\n".join(parser.blocks)
    if len(text) < 200:
        visible = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        visible = re.sub(r"(?s)<[^>]+>", " ", visible)
        text = clean_space(visible)
    extra = video_caption(current)
    if extra:
        text = f"{extra}\n\n{text}".strip()
    kind = "video" if is_video(current) else "page"
    if not text and not parser.description and not title:
        raise ValueError("No readable text on that page.")
    combined = "\n\n".join(part for part in (parser.description, text) if part)
    return {
        "url": current,
        "title": title or current,
        "kind": kind,
        "text": combined[:TEXT_LIMIT].strip(),
    }


def is_video(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    host = host.lower()
    return any(token in host for token in ("youtube.com", "youtu.be", "vimeo.com"))


def video_caption(url: str) -> str:
    if not is_video(url):
        return ""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if "vimeo.com" in host:
        endpoint = "https://vimeo.com/api/oembed.json?url=" + urllib.parse.quote(url, safe="")
    else:
        endpoint = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
    try:
        with urllib.request.urlopen(endpoint, timeout=FETCH_TIMEOUT) as response:
            payload = json.loads(response.read(100_000).decode("utf-8", errors="replace"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return ""
    title = clean_space(str(payload.get("title", "")))
    author = clean_space(str(payload.get("author_name", "")))
    bits = [bit for bit in (title, author) if bit]
    if not bits:
        return ""
    return "Video: " + " — ".join(bits) + ". Transcript was not available, so use only this title and the page text."


def source_block(sources: list[dict[str, str]]) -> str:
    if not sources:
        return "None provided. Write from the topics only, and do not invent facts."
    chunks = []
    for index, source in enumerate(sources, start=1):
        kind = "Video page" if source["kind"] == "video" else "Web page"
        chunks.append(
            f"[{index}] {kind}: {source['title']}\nURL: {source['url']}\n{source['text']}"
        )
    return "\n\n".join(chunks)


def build_prompt(company: str, topics: list[str], sources: list[dict[str, str]]) -> str:
    company_line = company or "Not specified"
    topic_line = "; ".join(topics)
    return f"""Company: {company_line}
Topics: {topic_line}

Source excerpts:
{source_block(sources)}

Return exactly two sections, in this order, with nothing before the first marker.

{ARTICLE_MARK}
The first line is the article title and nothing else.
Then a blank line.
Then a LinkedIn article of 500 to 700 words. Use short paragraphs. Stay specific to the topics. End with one question for the reader.

{SHORT_MARK}
A LinkedIn post of 90 to 140 words. The first line is a hook and can stand alone. Use plain paragraphs. End with one question, then a blank line and exactly 3 hashtags based on the topics.
"""


def split_draft(text: str) -> tuple[str, str]:
    cleaned = text.replace("```", "").strip()
    article_at = cleaned.find(ARTICLE_MARK)
    short_at = cleaned.find(SHORT_MARK)
    if article_at == -1 and short_at == -1:
        return cleaned, ""
    if short_at == -1:
        article = cleaned[article_at + len(ARTICLE_MARK) :].strip()
        return article, ""
    if article_at == -1 or short_at < article_at:
        short = cleaned[short_at + len(SHORT_MARK) :].strip()
        before = cleaned[:short_at].replace(ARTICLE_MARK, "").strip()
        return before, short
    article = cleaned[article_at + len(ARTICLE_MARK) : short_at].strip()
    short = cleaned[short_at + len(SHORT_MARK) :].strip()
    return article, short


def ollama_payload(model: str, prompt: str, stream: bool) -> dict:
    payload: dict = {
        "model": model,
        "stream": stream,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.5, "num_predict": 1800, "num_ctx": 8192},
        "keep_alive": "10m",
    }
    # Gemma 4 thinks by default. This tool needs the finished draft, not the reasoning trace.
    if model.startswith("gemma"):
        payload["think"] = False
    return payload


def installed_models() -> list[str]:
    with urllib.request.urlopen(OLLAMA_TAGS, timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    names = []
    for model in payload.get("models", []):
        name = str(model.get("name", ""))
        if name:
            names.append(name)
    return names


def model_ready(installed: list[str], model_id: str) -> bool:
    return any(name == model_id or name.startswith(model_id + ":") for name in installed)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/health":
            self.handle_health()
            return
        if path == "/":
            self.serve_file("index.html", "text/html; charset=utf-8")
            return
        if path in {"/styles.css", "/app.js"}:
            content_type = "text/css; charset=utf-8" if path.endswith(".css") else "text/javascript; charset=utf-8"
            self.serve_file(path.lstrip("/"), content_type)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if urllib.parse.urlparse(self.path).path != "/api/generate":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 100_000:
            self.send_json(413, {"error": "That request is too large."})
            return
        try:
            incoming = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_json(400, {"error": "The form data was not valid JSON."})
            return
        try:
            model, company, topics, urls = read_form(incoming)
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return
        self.stream_draft(model, company, topics, urls)

    def handle_health(self) -> None:
        try:
            installed = installed_models()
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            self.send_json(200, {"ollama": False, "models": []})
            return
        ready = [model["id"] for model in MODELS if model_ready(installed, model["id"])]
        self.send_json(200, {"ollama": True, "models": ready})

    def serve_file(self, name: str, content_type: str) -> None:
        file_path = (STATIC_DIR / name).resolve()
        try:
            file_path.relative_to(STATIC_DIR)
        except ValueError:
            self.send_error(404)
            return
        if not file_path.is_file():
            self.send_error(404)
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def stream_draft(self, model: str, company: str, topics: list[str], urls: list[str]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        sources: list[dict[str, str]] = []
        notes: list[dict[str, str]] = []
        try:
            for url in urls:
                self.write_event({"type": "status", "message": f"Reading {url}"})
                try:
                    source = fetch_url(url)
                except ValueError as exc:
                    notes.append({"url": url, "error": str(exc)})
                    continue
                sources.append(source)
                notes.append({"url": source["url"], "title": source["title"], "kind": source["kind"]})
            self.write_event({"type": "status", "message": f"Writing with {model}"})
            prompt = build_prompt(company, topics, sources)
            request = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(ollama_payload(model, prompt, stream=True)).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            collected: list[str] = []
            with urllib.request.urlopen(request, timeout=600) as response:
                for raw_line in response:
                    if not raw_line.strip():
                        continue
                    event = json.loads(raw_line.decode("utf-8"))
                    if event.get("error"):
                        raise RuntimeError(str(event["error"]))
                    token = str(event.get("message", {}).get("content") or "")
                    if token:
                        collected.append(token)
                        self.write_event({"type": "token", "text": token})
                    if event.get("done"):
                        break
            article, short = split_draft("".join(collected))
            self.write_event(
                {
                    "type": "done",
                    "article": article,
                    "short": short,
                    "sources": notes,
                }
            )
        except BrokenPipeError:
            return
        except urllib.error.URLError as exc:
            self.write_event({"type": "error", "message": f"Ollama is not reachable at 127.0.0.1:11434 ({exc.reason})."})
        except (TimeoutError, json.JSONDecodeError, RuntimeError, OSError) as exc:
            self.write_event({"type": "error", "message": str(exc) or "The draft stopped before it finished."})
        finally:
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                pass

    def write_event(self, payload: dict) -> None:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        self.wfile.write(f"{len(data):X}\r\n".encode("ascii"))
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
        self.wfile.flush()


def read_form(incoming: dict) -> tuple[str, str, list[str], list[str]]:
    model = str(incoming.get("model", "")).strip()
    if model not in MODEL_IDS:
        raise ValueError("Choose Mistral Small 3.2 or Gemma 4 12B.")
    company = clean_space(str(incoming.get("company", "")))[:120]
    topics = parse_lines(str(incoming.get("topics", "")))
    if not topics:
        raise ValueError("Add at least one topic.")
    if len(topics) > 12:
        raise ValueError("Use 12 topics or fewer.")
    urls = parse_lines(str(incoming.get("urls", "")))
    if len(urls) > MAX_URLS:
        raise ValueError(f"Use {MAX_URLS} links or fewer.")
    for url in urls:
        validate_public_url(url)
    return model, company, topics, urls


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"LinkedIn drafts at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
