"""Animated explainer storyboards, built from a finished draft or from scripts.

A draft becomes one portrait diagram: a headline, nodes that connect one beat at
a time, and a short line at the bottom that changes. A set of scripts becomes a
sequence of cards, each with a layout picked from what its script says. Labels
come from the words given. Nothing is added that the script did not say.
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

SCENE_SECONDS = 11.0
SCENE_TAIL = 1.6
MAX_SCENES = 10
MAX_SCENE_CHARS = 1200
LAYOUTS = ("auto", "statement", "steps", "compare", "diagram", "checklist", "question")
LAYOUT_NAMES = {
    "statement": "Statement",
    "steps": "Steps",
    "compare": "Compare",
    "diagram": "Diagram",
    "checklist": "Checklist",
    "question": "Question",
}
_NUMBERED = re.compile(r"^\s*(?:\d+[.)]|step\s+\d+[:.)]?)\s+", re.I)
_BULLET = re.compile(r"^\s*[-*•]\s+")
_ORDINAL = re.compile(
    r"^(?:first|second|third|fourth|fifth|then|next|after that|finally|lastly)\b[,:]?\s*", re.I
)
_TURN = re.compile(
    r"^(?:that is why|that's why|this is why|that is where|that's where|so|instead|now|but|"
    r"however|the answer|here is|here's)\b[,:]?\s*",
    re.I,
)
_PREFIX = re.compile(r"^([^:]{2,40}):\s+(.{3,})$")
_CONTRAST = (
    (re.compile(r"\binstead of\b", re.I), "after_left"),
    (re.compile(r"\brather than\b", re.I), "after_left"),
    (re.compile(r"\s(?:vs\.?|versus)\s", re.I), "before_left"),
    (re.compile(r",\s+not\s+", re.I), "after_left"),
)
_ACTIONS = {
    "add", "ask", "audit", "automate", "book", "build", "check", "choose", "come", "comment",
    "define", "document", "download", "find", "fix", "follow", "give", "join", "keep", "learn",
    "limit", "log", "make", "map", "measure", "meet", "monitor", "own", "plan", "protect", "put",
    "read", "register", "review", "run", "scope", "secure", "see", "set", "ship", "show", "sign",
    "start", "stop", "tell", "test", "track", "try", "use", "verify", "visit", "watch", "write",
}
_INVITES = {
    "book", "come", "comment", "download", "follow", "join", "learn", "meet", "read", "register",
    "see", "sign", "try", "visit", "watch",
}


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
    headline_limit = 8 if len(parts[headline_at].split()) > 12 else 16
    headline = clean_title(parts[headline_at], headline_limit, keep_question="?" in parts[headline_at])
    if len(headline.split()) < 3:
        raise ValueError("The script needs a headline of at least three words.")
    headline_key = headline.casefold().rstrip(".?")
    labels: list[str] = []
    statements: list[str] = []
    questions: list[str] = []
    # A title line is only the headline. A full sentence is also one of the boxes.
    sources = list(parts[headline_at + 1 :])
    opening = parts[headline_at].rstrip()
    if opening.endswith((".", "!", "?")):
        sources.insert(0, opening)
    for part in sources:
        question = "?" in part
        point = _point(part)
        if len(point.split()) >= 3:
            if question:
                questions.append(point)
            else:
                statements.append(point)
        if not question and len(labels) < 6:
            _add_label(labels, _box_label(part), headline_key)
    if len(labels) < 3:
        raise ValueError(
            "The diagram needs three boxes. Add another sentence on its own line."
        )
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


def _point(value: str) -> str:
    """The claim in a sentence. A colon usually introduces it."""
    text = clean_text(value)
    if ":" in text:
        tail = text.split(":")[-1].strip()
        if len(tail.split()) >= 3:
            return tail
    return text


def _box_label(value: str) -> str:
    """A short box. A brief line keeps its opening words. A long sentence keeps its claim."""
    raw = clean_text(value)
    point = _point(value)
    if point != raw and len(point.split()) <= 12:
        return clean_title(point, 12)
    if len(point.split()) <= 8:
        label = _content_label(point)
        if len(label.split()) >= 2:
            return label
    return clean_title(point, 12)


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


def scenes_from_payload(incoming: object) -> list[dict]:
    """Plan every card that has a script. A card that cannot be built carries its error."""
    if not isinstance(incoming, dict) or not isinstance(incoming.get("scenes"), list):
        raise ValueError("The cards were not valid.")
    raw = incoming["scenes"]
    if len(raw) > MAX_SCENES:
        raise ValueError(f"Use {MAX_SCENES} cards or fewer.")
    filled: list[tuple[int, str, str]] = []
    for number, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("The cards were not valid.")
        script = str(item.get("script") or "")
        if len(script) > MAX_SCENE_CHARS:
            raise ValueError(f"Card {number} is longer than {MAX_SCENE_CHARS} characters.")
        if script.strip():
            filled.append((number, script, str(item.get("layout") or "auto")))
    if not filled:
        raise ValueError("Write a script in at least one card.")
    results: list[dict] = []
    for position, (number, script, layout) in enumerate(filled, start=1):
        try:
            board, plan = storyboard_from_scene(script, layout, position, len(filled))
        except ValueError as exc:
            results.append({"card": number, "error": str(exc)})
            continue
        results.append({"card": number, "motion": board, "plan": plan})
    return results


def storyboard_from_scene(
    script: str,
    layout: str = "auto",
    position: int = 1,
    count: int = 1,
) -> tuple[dict, dict]:
    """One card of the video. The layout follows the script unless one was chosen."""
    parts, marks = _scene_parts(script)
    if not parts:
        raise ValueError("Write a script for this card.")
    eyebrow, parts = _split_eyebrow(parts)
    wanted = layout if layout in LAYOUTS else "auto"
    guessed = _intent(parts, marks)
    picked = guessed if wanted == "auto" else wanted
    note = ""
    built = _build(picked, parts, marks, eyebrow, script)
    if built is None and picked != guessed:
        note = f"{LAYOUT_NAMES[picked]} needs more lines, so this card uses {LAYOUT_NAMES[guessed]}."
        picked = guessed
        built = _build(picked, parts, marks, eyebrow, script)
    if built is None and picked != "statement":
        if not note and wanted != "auto":
            note = f"{LAYOUT_NAMES[wanted]} needs more lines, so this card uses Statement."
        picked = "statement"
        built = _build(picked, parts, marks, eyebrow, script)
    if built is None:
        raise ValueError("Write at least one sentence of three words or more.")
    board, plan = built
    beats = len(board["beats"]) or 1
    seconds = round((SCENE_SECONDS - SCENE_TAIL) / beats, 3)
    board.update({
        "layout": picked,
        "seconds": seconds,
        "tail": round(SCENE_SECONDS - beats * seconds, 3),
        "fade": True,
        "position": position,
        "count": count,
    })
    board.setdefault("columns", ["", ""])
    plan.update({
        "layout": picked,
        "name": LAYOUT_NAMES[picked],
        "note": note,
        "seconds": SCENE_SECONDS,
    })
    return board, plan


def _scene_parts(script: str) -> tuple[list[str], dict[str, int]]:
    raw = _clip(script, MAX_SCENE_CHARS).replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    marks = {"numbered": 0, "bulleted": 0}
    for line in raw.split("\n"):
        if not line.strip():
            continue
        if _NUMBERED.match(line):
            marks["numbered"] += 1
            line = _NUMBERED.sub("", line, count=1)
        elif _BULLET.match(line):
            marks["bulleted"] += 1
            line = _BULLET.sub("", line, count=1)
        cleaned = clean_text(line)
        if not cleaned:
            continue
        bits = [bit.strip() for bit in _SENTENCE.split(cleaned) if bit.strip()]
        parts.extend(bits or [cleaned])
        if len(parts) >= 16:
            break
    return parts[:16], marks


def _split_eyebrow(parts: list[str]) -> tuple[str, list[str]]:
    if (
        len(parts) >= 2
        and 1 <= len(parts[0].split()) <= 4
        and parts[0][-1:] not in ".?!:"
        and len(parts[1].split()) >= 5
    ):
        return clean_text(parts[0])[:36], parts[1:]
    return "", parts


def _title_and_body(parts: list[str]) -> tuple[str, list[str]]:
    """A first line with no closing period is a title when more lines follow."""
    if len(parts) > 1:
        first = parts[0].rstrip()
        bare = first[-1:] not in ".!?"
        if (bare or first.endswith(":")) and len(first.split()) <= 14:
            return first.rstrip(":").strip(), parts[1:]
    return "", list(parts)


def _is_invite(part: str) -> bool:
    words = clean_text(part).split()
    return bool(words) and words[0].casefold().strip(".,;:") in _INVITES


def _is_action(part: str) -> bool:
    words = clean_text(part).split()
    return bool(words) and words[0].casefold().strip(".,;:") in _ACTIONS


def _closing(body: list[str]) -> tuple[list[str], str]:
    """A last question or invitation is the line at the bottom, not an item."""
    if len(body) >= 2 and ("?" in body[-1] or _is_invite(body[-1])):
        return body[:-1], body[-1]
    return body, ""


def _intent(parts: list[str], marks: dict[str, int]) -> str:
    title, body = _title_and_body(parts)
    items, closing = _closing(body)
    items = [part for part in items if "?" not in part]
    if _compare_split(parts) is not None:
        return "compare"
    if marks.get("numbered", 0) >= 2 or sum(1 for part in items if _ORDINAL.match(part)) >= 2:
        return "steps"
    questions = [part for part in parts if "?" in part]
    if len(items) <= 1:
        return "question" if questions else "statement"
    if marks.get("bulleted", 0) >= 2:
        return "checklist"
    if len(items) >= 3 and sum(1 for part in items if _is_action(part)) * 2 > len(items):
        return "checklist"
    if len(items) == 2 and not title and all(len(part.split()) <= 12 for part in items):
        return "statement"
    if len(items) >= 3 and sum(len(part.split()) for part in items) / len(items) <= 9:
        return "diagram"
    return "steps"


def _build(
    layout: str,
    parts: list[str],
    marks: dict[str, int],
    eyebrow: str,
    script: str,
) -> tuple[dict, dict] | None:
    if layout == "statement":
        return _build_statement(parts, eyebrow)
    if layout == "question":
        return _build_question(parts, eyebrow)
    if layout == "steps":
        return _build_stack(parts, eyebrow, "step", 5)
    if layout == "checklist":
        return _build_stack(parts, eyebrow, "check", 6)
    if layout == "compare":
        return _build_compare(parts, eyebrow)
    if layout == "diagram":
        return _build_diagram(script)
    return None


def _scene_board(headline: str, eyebrow: str, nodes: list[dict], edges: list[dict], beats: list[dict]) -> dict:
    words = [node["label"] for node in nodes]
    return {
        "headline": headline,
        "eyebrow": eyebrow,
        "emphasis": _emphasis(headline, words) if headline else [],
        "seconds": BEAT_SECONDS,
        "tail": TAIL_SECONDS,
        "nodes": nodes,
        "edges": edges,
        "beats": beats,
        "columns": ["", ""],
    }


def _scene_plan(headline: str, eyebrow: str, items: list[str], captions: list[str]) -> dict:
    return {"headline": headline, "eyebrow": eyebrow, "items": items, "captions": captions}


def _label(value: str, limit: int) -> str:
    text = clean_title(value, limit)
    return text[:1].upper() + text[1:] if text else text


def _bottom_lines(values: list[str], headline: str, limit: int = 2) -> list[str]:
    key = headline.casefold().rstrip(".?")
    lines: list[str] = []
    for value in values:
        _add_caption(lines, value, key, limit=14)
        if len(lines) == limit:
            break
    return lines


def _build_statement(parts: list[str], eyebrow: str) -> tuple[dict, dict] | None:
    statements = [part for part in parts if "?" not in part]
    questions = [part for part in parts if "?" in part]
    if not statements:
        return None
    headline = clean_title(statements[0].rstrip(":"), 24)
    if len(headline.split()) < 3:
        return None
    captions = _bottom_lines(statements[1:3] + questions[-1:], headline, limit=3)
    beats = [{"caption": caption, "reveal": []} for caption in captions] or [{"caption": "", "reveal": []}]
    board = _scene_board(headline, eyebrow, [], [], beats)
    return board, _scene_plan(headline, eyebrow, [], captions)


def _build_question(parts: list[str], eyebrow: str) -> tuple[dict, dict] | None:
    questions = [part for part in parts if "?" in part]
    if not questions:
        return None
    asked = questions[-1]
    headline = clean_title(asked, 20, keep_question=True)
    if len(headline.split()) < 3:
        return None
    nodes = [
        {"id": f"n{index + 1}", "label": option, "place": "option", "tone": "neutral"}
        for index, option in enumerate(_options(asked))
    ]
    others = [part for part in parts if part is not asked and "?" not in part]
    captions = _bottom_lines(others, headline, limit=2)
    beats = [{"caption": "", "reveal": []}]
    if nodes:
        beats.append({"caption": "", "reveal": [node["id"] for node in nodes]})
    beats.extend({"caption": caption, "reveal": []} for caption in captions)
    board = _scene_board(headline, eyebrow, nodes, [], beats)
    return board, _scene_plan(headline, eyebrow, [node["label"] for node in nodes], captions)


def _options(question: str) -> list[str]:
    """Two choices named in an either-or question."""
    text = clean_text(question).rstrip("?").strip()
    if not re.search(r"\sor\s", text, re.I):
        return []
    left, right = re.split(r",?\s+or\s+", text, maxsplit=1, flags=re.I)
    left = re.split(r"[,:;]", left)[-1].strip()
    words = left.split()
    for index in range(len(words) - 1, -1, -1):
        if words[index].casefold() in {"with", "from", "on", "in", "at", "to", "for", "by", "about", "between"}:
            words = words[index + 1 :]
            break
    if len(words) > 5:
        words = words[-3:]
    choice = " ".join(words).strip(" ,;:")
    other = " ".join(right.split()[:5]).strip(" ,;:")
    if not choice or not other or choice.casefold() == other.casefold():
        return []
    return [_label(choice, 6), _label(other, 6)]


def _build_stack(parts: list[str], eyebrow: str, place: str, limit: int) -> tuple[dict, dict] | None:
    title, body = _title_and_body(parts)
    items, closing = _closing(body)
    labels: list[str] = []
    for part in items:
        if "?" in part:
            continue
        label = _label(_ORDINAL.sub("", part, count=1), 16 if place == "step" else 12)
        if len(label.split()) >= 2 and all(label.casefold() != old.casefold() for old in labels):
            labels.append(label)
        if len(labels) == limit:
            break
    if len(labels) < 2:
        return None
    headline = clean_title(title, 12) if title else ""
    nodes = [
        {"id": f"n{index + 1}", "label": label, "place": place, "tone": "neutral", "order": index + 1}
        for index, label in enumerate(labels)
    ]
    if place == "check" and len(nodes) == 6:
        groups = [nodes[0:2], nodes[2:4], nodes[4:6]]
    else:
        groups = [[node] for node in nodes]
    beats = [{"caption": "", "reveal": [node["id"] for node in group]} for group in groups]
    captions = _bottom_lines([closing], headline, limit=1) if closing else []
    if captions:
        beats.append({"caption": captions[0], "reveal": []})
    edges = []
    if place == "step":
        edges = [
            {"from": nodes[index]["id"], "to": nodes[index + 1]["id"], "tone": "neutral", "beat": index + 1}
            for index in range(len(nodes) - 1)
        ]
    board = _scene_board(headline, eyebrow, nodes, edges, beats)
    return board, _scene_plan(headline, eyebrow, labels, captions)


def _compare_split(parts: list[str]) -> tuple[str, list[str], list[str], list[str], str] | None:
    """Title, left lines, right lines, column labels, and the closing line."""
    title, body = _title_and_body(parts)
    items, closing = _closing(body)
    if not items:
        return None
    prefixed = [_PREFIX.match(part) for part in items]
    if len(items) >= 2 and all(prefixed):
        keys: list[str] = []
        names: list[str] = []
        for match in prefixed:
            name = match.group(1).strip()
            if len(name.split()) > 5:
                keys = []
                break
            if name.casefold() not in keys:
                keys.append(name.casefold())
                names.append(name)
        if len(keys) == 2:
            left = [m.group(2) for m in prefixed if m.group(1).strip().casefold() == keys[0]]
            right = [m.group(2) for m in prefixed if m.group(1).strip().casefold() == keys[1]]
            return title, left, right, names, closing
    for index, part in enumerate(items):
        if index >= 1 and _TURN.match(part):
            turned = _TURN.sub("", part, count=1).strip()
            if len(turned.split()) >= 3:
                return title, items[:index], [turned, *items[index + 1 :]], ["", ""], closing
    if len(items) == 1:
        sentence = clean_text(items[0]).rstrip(".")
        for pattern, order in _CONTRAST:
            pieces = pattern.split(sentence, maxsplit=1)
            if len(pieces) != 2:
                continue
            first, second = pieces[0].strip(" ,"), pieces[1].strip(" ,")
            if len(first.split()) < 2 or len(second.split()) < 2:
                continue
            if order == "after_left":
                return title, [second], [first], ["", ""], closing
            return title, [first], [second], ["", ""], closing
    return None


def _column(lines: list[str]) -> list[str]:
    labels: list[str] = []
    for line in lines:
        pieces = [line]
        if ":" in line:
            head, tail = line.split(":", 1)
            if len(head.split()) >= 3 and len(tail.split()) >= 3:
                pieces = [head, tail]
        for piece in pieces:
            label = _label(piece, 20)
            if len(label.split()) >= 2:
                labels.append(label)
            if len(labels) == 3:
                return labels
    return labels


def _build_compare(parts: list[str], eyebrow: str) -> tuple[dict, dict] | None:
    split = _compare_split(parts)
    if split is None:
        return None
    title, left_lines, right_lines, names, closing = split
    left = _column(left_lines)
    right = _column(right_lines)
    if not left or not right:
        return None
    headline = clean_title(title, 12) if title else ""
    nodes = [
        {"id": f"n{index + 1}", "label": label, "place": "left", "tone": "muted"}
        for index, label in enumerate(left)
    ]
    nodes.extend(
        {"id": f"n{len(left) + index + 1}", "label": label, "place": "right", "tone": "good"}
        for index, label in enumerate(right)
    )
    beats = [
        {"caption": "", "reveal": [node["id"] for node in nodes if node["place"] == "left"]},
        {"caption": "", "reveal": [node["id"] for node in nodes if node["place"] == "right"]},
    ]
    captions = _bottom_lines([closing], headline, limit=1) if closing else []
    if captions:
        beats.append({"caption": captions[0], "reveal": []})
    board = _scene_board(headline, eyebrow, nodes, [], beats)
    board["columns"] = [clean_text(name)[:28] for name in names] if any(names) else ["", ""]
    return board, _scene_plan(headline, eyebrow, left + right, captions)


def _build_diagram(script: str) -> tuple[dict, dict] | None:
    try:
        board, plan = storyboard_from_script(script)
    except ValueError:
        return None
    board["columns"] = ["", ""]
    return board, _scene_plan(plan["headline"], plan["eyebrow"], plan["nodes"], plan["captions"])
