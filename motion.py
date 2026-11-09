"""Animated explainer storyboard, built from a finished draft or from a script.

The picture is a portrait diagram: a headline, nodes that connect one beat at a
time, and a short line at the bottom that changes. Labels are shortened card
titles. Nothing is added that the draft did not already say.
"""

from __future__ import annotations

import re

from cards import clean_text, clean_title

BEAT_SECONDS = 3.2
TAIL_SECONDS = 1.4
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_ALERT = re.compile(
    r"\b(attack|attacker|attacks|breach|breaches|exploit|exploits|exploitation|"
    r"compromise|compromised|threat|threats|recon|malware|intruder|intrusion)\b",
    re.I,
)
_STOP = {
    "that", "this", "with", "from", "your", "have", "more", "than", "into",
    "about", "would", "could", "their", "there", "what", "when", "where",
    "which", "while", "does", "doing", "they", "them", "then", "been", "were",
    "will", "just", "only", "still", "over", "under", "such", "each", "some",
}
_LEAD = {"a", "an", "the", "your", "our", "its", "their"}


def storyboard_from_deck(deck: dict, article: str, short: str, topics: list[str] | None = None) -> dict:
    """Return a drawable storyboard, or an empty one when the draft is too thin."""
    empty = _empty()
    slides = deck.get("slides") if isinstance(deck, dict) else None
    if not isinstance(slides, list):
        return empty
    hook = next((slide for slide in slides if isinstance(slide, dict) and slide.get("kind") == "hook"), None)
    headline = clean_title(str((hook or {}).get("title") or ""), 16)
    if len(headline.split()) < 3:
        return empty
    labels = _labels(slides, headline)
    if len(labels) < 3:
        return empty
    nodes = _nodes(labels)
    beats, edges = _beats_and_edges(nodes, _captions(short, article, headline))
    if not beats:
        return empty
    return {
        "headline": headline,
        "eyebrow": clean_text(str(deck.get("eyebrow") or ""))[:36],
        "emphasis": _emphasis(headline, topics or []),
        "seconds": BEAT_SECONDS,
        "tail": TAIL_SECONDS,
        "nodes": nodes,
        "edges": edges,
        "beats": beats,
    }


def _empty() -> dict:
    return {
        "headline": "",
        "eyebrow": "",
        "emphasis": [],
        "seconds": BEAT_SECONDS,
        "tail": TAIL_SECONDS,
        "nodes": [],
        "edges": [],
        "beats": [],
    }


def _labels(slides: list, headline: str) -> list[str]:
    headline_key = headline.casefold()
    found: list[str] = []

    def add(value: str) -> None:
        label = _short_label(value)
        key = label.casefold()
        if len(label.split()) < 2 or key == headline_key:
            return
        for index, old in enumerate(found):
            old_key = old.casefold()
            if key == old_key or key.startswith(old_key) or old_key.startswith(key):
                if len(label) < len(old):
                    found[index] = label
                return
        found.append(label)

    points = [slide for slide in slides if isinstance(slide, dict) and slide.get("kind") == "point"]
    for slide in points:
        add(str(slide.get("title") or ""))
        if len(found) == 6:
            return found
    for slide in slides:
        if not isinstance(slide, dict) or slide.get("kind") != "checklist":
            continue
        for item in slide.get("items") or []:
            add(str(item))
            if len(found) == 6:
                return found
    return found


def _short_label(value: str) -> str:
    """Keep the opening words of a card title, and stop before a preposition."""
    glue = _LEAD | {
        "and", "or", "to", "of", "for", "with", "from", "into", "through", "over",
        "after", "before", "than", "that", "this", "on", "in", "at", "by", "as",
    }
    aux = {"is", "are", "was", "were", "be", "been", "being", "has", "have", "had"}
    words = clean_text(value).rstrip(".?").split()
    kept: list[str] = []
    for word in words:
        bare = word.casefold().strip(".,;:")
        if bare in {"a", "an", "the"}:
            continue
        if bare in glue or bare in aux:
            if len(kept) >= 2:
                break
            if not kept or bare in glue:
                continue
        kept.append(word)
        if len(kept) == 3:
            break
    return " ".join(kept)


def _nodes(labels: list[str]) -> list[dict]:
    alert_at = [index for index, label in enumerate(labels) if _ALERT.search(label)]
    side_index = alert_at[-1] if alert_at else (len(labels) - 1 if len(labels) >= 4 else None)
    side = labels[side_index] if side_index is not None else ""
    rest = [label for index, label in enumerate(labels) if index != side_index]
    others = rest[1:]
    top_count = (len(others) + 1) // 2 if others else 0
    top = others[:top_count]
    bottom = others[top_count:]
    nodes: list[dict] = []

    def add(label: str, place: str, tone: str = "neutral") -> None:
        nodes.append({
            "id": f"n{len(nodes) + 1}",
            "label": label,
            "place": place,
            "tone": tone,
        })

    add(rest[0], "hub")
    for label in top:
        add(label, "top")
    for label in bottom:
        add(label, "bottom")
    if side:
        add(side, "side", "alert" if _ALERT.search(side) else "neutral")
    return nodes


def _beats_and_edges(nodes: list[dict], captions: list[str]) -> tuple[list[dict], list[dict]]:
    hub = next(node for node in nodes if node["place"] == "hub")
    groups = [[node for node in nodes if node["place"] in {"hub", "top"}]]
    bottom = [node for node in nodes if node["place"] == "bottom"]
    side = [node for node in nodes if node["place"] == "side"]
    if bottom:
        groups.append(bottom)
    if side:
        groups.append(side)
    if not captions:
        captions = [hub["label"]]
    while len(captions) < len(groups):
        captions.append(captions[-1])

    beats = [
        {"caption": captions[index], "reveal": [node["id"] for node in group]}
        for index, group in enumerate(groups)
    ]
    for caption in captions[len(groups):]:
        if caption != beats[-1]["caption"]:
            beats.append({"caption": caption, "reveal": []})
    edges = [
        {"from": node["id"], "to": hub["id"], "tone": "neutral", "beat": 0}
        for node in nodes
        if node["place"] == "top"
    ]
    if bottom:
        edges.extend(
            {"from": hub["id"], "to": node["id"], "tone": "neutral", "beat": 1}
            for node in bottom
        )
    if side:
        tone = side[0]["tone"]
        side_beat = len(groups) - 1
        edges.append({"from": side[0]["id"], "to": hub["id"], "tone": tone, "beat": side_beat})
        if bottom and tone == "alert":
            edges.append({"from": side[0]["id"], "to": bottom[-1]["id"], "tone": tone, "beat": side_beat})
    return beats, edges


def _captions(short: str, article: str, headline: str) -> list[str]:
    headline_key = headline.casefold().rstrip(".?")
    chosen: list[str] = []
    seen: set[str] = set()
    pool = _sentences(short) + _sentences(article)
    short_enough = [line for line in pool if 3 <= len(line.split()) <= 14]
    longer = [line for line in pool if len(line.split()) > 14]
    for line in short_enough + longer:
        caption = clean_title(line, 12, keep_question="?" in line)
        key = caption.casefold().rstrip(".?")
        if len(caption.split()) < 3 or key in seen or key == headline_key:
            continue
        seen.add(key)
        chosen.append(caption)
        if len(chosen) == 3:
            break
    return chosen


def _sentences(text: str) -> list[str]:
    found = []
    for chunk in re.split(r"\n+", text or ""):
        cleaned = clean_text(chunk)
        if not cleaned:
            continue
        parts = [part.strip() for part in _SENTENCE.split(cleaned) if part.strip()]
        found.extend(parts or [cleaned])
    return found


def storyboard_from_script(script: str) -> tuple[dict, dict]:
    """Build a storyboard from a free-form script. The plan is the editable text."""
    parts = _script_parts(script)
    if not parts:
        raise ValueError("Paste a script first.")
    eyebrow = ""
    if (
        len(parts) >= 2
        and 1 <= len(parts[0].split()) <= 4
        and parts[0][-1:] not in ".?!"
        and len(parts[1].split()) >= 5
    ):
        eyebrow = clean_text(parts[0])[:36]
        parts = parts[1:]
    headline_at = next((index for index, part in enumerate(parts) if len(part.split()) >= 3), None)
    if headline_at is None:
        raise ValueError("The script needs a headline of at least three words.")
    headline = clean_title(parts[headline_at], 16, keep_question="?" in parts[headline_at])
    if len(headline.split()) < 3:
        raise ValueError("The script needs a headline of at least three words.")
    headline_key = headline.casefold().rstrip(".?")
    labels: list[str] = []
    statements: list[str] = []
    questions: list[str] = []
    for part in parts[headline_at + 1 :]:
        question = "?" in part
        if len(part.split()) >= 3:
            if question:
                questions.append(part)
            else:
                statements.append(part)
        if not question and len(labels) < 6:
            label = _content_label(part)
            if len(label.split()) < 2:
                label = clean_title(part, 4)
            _add_label(labels, label, headline_key)
    if len(labels) < 3:
        raise ValueError("Add at least three more lines. Each one becomes a box in the diagram.")
    captions: list[str] = []
    room = 4 - (1 if questions else 0)
    for part in statements[:room]:
        _add_caption(captions, part, headline_key)
    if questions:
        _add_caption(captions, questions[-1], headline_key)
    return _finish(headline, eyebrow, labels[:6], captions)


def storyboard_from_plan(headline: str, eyebrow: str, nodes: object, captions: object) -> tuple[dict, dict]:
    """Rebuild the storyboard from the lines the user edited."""
    if not isinstance(nodes, list) or not isinstance(captions, list):
        raise ValueError("The video plan was not valid.")
    title = clean_title(_clip(headline, 300), 16, keep_question="?" in str(headline or ""))
    if len(title.split()) < 3:
        raise ValueError("The headline needs at least three words.")
    kicker = clean_text(_clip(eyebrow, 80))[:36]
    headline_key = title.casefold().rstrip(".?")
    labels: list[str] = []
    for item in nodes[:8]:
        _add_exact(labels, clean_title(_clip(item, 200), 8), headline_key)
        if len(labels) == 6:
            break
    if len(labels) < 3:
        raise ValueError("Add at least three boxes, one per line, with at least two words each.")
    lines: list[str] = []
    for item in captions[:6]:
        _add_caption(lines, _clip(item, 300), headline_key, limit=14)
        if len(lines) == 4:
            break
    return _finish(title, kicker, labels, lines)


def _finish(headline: str, eyebrow: str, labels: list[str], captions: list[str]) -> tuple[dict, dict]:
    nodes = _nodes_from_labels(labels)
    beats, edges = _beats_and_edges(nodes, list(captions))
    if not beats:
        raise ValueError("The script did not include enough text to build the video.")
    board = {
        "headline": headline,
        "eyebrow": eyebrow,
        "emphasis": _emphasis(headline, labels),
        "seconds": BEAT_SECONDS,
        "tail": TAIL_SECONDS,
        "nodes": nodes,
        "edges": edges,
        "beats": beats,
    }
    plan = {"headline": headline, "eyebrow": eyebrow, "nodes": labels, "captions": captions}
    return board, plan


def _clip(value: object, limit: int) -> str:
    return str(value or "")[:limit]


def _script_parts(script: str) -> list[str]:
    raw = _clip(script, 4000).replace("\r\n", "\n").replace("\r", "\n").strip()
    parts: list[str] = []
    for line in re.split(r"\n+", raw):
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line).strip()
        cleaned = clean_text(line)
        if not cleaned:
            continue
        if len(cleaned.split()) > 18:
            bits = [bit.strip() for bit in _SENTENCE.split(cleaned) if bit.strip()]
            parts.extend(bits or [cleaned])
        else:
            parts.append(cleaned)
        if len(parts) >= 24:
            break
    return parts


def _content_label(value: str) -> str:
    """Opening words of a script line, skipping articles and helper verbs."""
    skip = _LEAD | {
        "and", "or", "to", "of", "for", "with", "from", "into", "through", "over",
        "after", "before", "than", "that", "this", "on", "in", "at", "by", "as",
        "is", "are", "was", "were", "be", "been", "being", "has", "have", "had",
    }
    kept: list[str] = []
    for word in clean_text(value).rstrip(".?").split():
        bare = word.casefold().strip(".,;:")
        if bare in skip:
            if len(kept) >= 2:
                break
            continue
        kept.append(word)
        if len(kept) == 3:
            break
    return " ".join(kept)


def _add_label(found: list[str], label: str, headline_key: str) -> None:
    label = clean_text(label)
    key = label.casefold()
    if len(label.split()) < 2 or key == headline_key:
        return
    for index, old in enumerate(found):
        old_key = old.casefold()
        if key == old_key or key.startswith(old_key) or old_key.startswith(key):
            if len(label) < len(old):
                found[index] = label
            return
    found.append(label)


def _add_exact(found: list[str], label: str, headline_key: str) -> None:
    label = clean_text(label)
    key = label.casefold()
    if len(label.split()) < 2 or key == headline_key or any(item.casefold() == key for item in found):
        return
    found.append(label)


def _add_caption(found: list[str], value: str, headline_key: str, limit: int = 12) -> None:
    caption = clean_title(clean_text(value), limit, keep_question="?" in str(value))
    key = caption.casefold().rstrip(".?")
    if len(caption.split()) < 3 or key == headline_key or any(item.casefold().rstrip(".?") == key for item in found):
        return
    found.append(caption)


def _nodes_from_labels(labels: list[str]) -> list[dict]:
    """First line stays the center box. A later attack line, or a fourth line, sits to the side."""
    tail = labels[1:]
    alert_at = [index for index, label in enumerate(tail) if _ALERT.search(label)]
    side_index = alert_at[-1] if alert_at else (len(tail) - 1 if len(labels) >= 4 else None)
    side = tail[side_index] if side_index is not None else ""
    rest = [label for index, label in enumerate(tail) if index != side_index]
    top_count = (len(rest) + 1) // 2 if rest else 0
    top = rest[:top_count]
    bottom = rest[top_count:]
    nodes: list[dict] = []

    def add(label: str, place: str, tone: str = "neutral") -> None:
        nodes.append({
            "id": f"n{len(nodes) + 1}",
            "label": label,
            "place": place,
            "tone": tone,
        })

    add(labels[0], "hub")
    for label in top:
        add(label, "top")
    for label in bottom:
        add(label, "bottom")
    if side:
        add(side, "side", "alert" if _ALERT.search(side) else "neutral")
    return nodes


def _emphasis(headline: str, topics: list[str]) -> list[str]:
    topic_words = {
        word.casefold()
        for topic in topics
        for word in clean_text(topic).split()
        if len(word) > 3
    }
    picked: list[str] = []
    for word in headline.split():
        bare = word.casefold().strip(".,;:?")
        if bare in topic_words and bare not in picked:
            picked.append(bare)
        if len(picked) == 3:
            return picked
    if picked:
        return picked
    ranked = sorted(
        (word.casefold().strip(".,;:?") for word in headline.split()),
        key=len,
        reverse=True,
    )
    for bare in ranked:
        if len(bare) > 4 and bare not in _STOP and bare not in picked:
            picked.append(bare)
        if len(picked) == 2:
            break
    return picked
