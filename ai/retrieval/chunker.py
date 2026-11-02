"""Heading-aware Markdown chunking with stable chunk ids (the citation targets)."""
import re
from dataclasses import dataclass, field

import yaml

from ai.text_utils import slugify

MAX_WORDS = 450      # ~600 tokens
OVERLAP_WORDS = 60   # ~80 tokens


@dataclass
class Chunk:
    id: str
    heading: str
    text: str
    meta: dict = field(default_factory=dict)


def parse_front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return yaml.safe_load(parts[1]) or {}, parts[2].lstrip("\n")
    return {}, text


def _split_by_heading(body: str) -> list[tuple[str, str]]:
    """Return (heading, text) pairs, never splitting inside fenced code blocks."""
    sections: list[tuple[str, list[str]]] = [("Introduction", [])]
    in_code = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m and not in_code:
            sections.append((m.group(2).strip(), []))
        else:
            sections[-1][1].append(line)
    return [(h, "\n".join(lines).strip()) for h, lines in sections if "\n".join(lines).strip()]


def _window(text: str) -> list[str]:
    words = text.split(" ")
    if len(words) <= MAX_WORDS or "```" in text:
        return [text]
    out, start = [], 0
    while start < len(words):
        out.append(" ".join(words[start:start + MAX_WORDS]))
        start += MAX_WORDS - OVERLAP_WORDS
    return out


def chunk_markdown(doc_slug: str, text: str, base_meta: dict | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, section_text in _split_by_heading(text):
        anchor = slugify(heading)
        for n, piece in enumerate(_window(section_text)):
            chunks.append(Chunk(id=f"{doc_slug}#{anchor}#{n}", heading=heading, text=f"## {heading}\n{piece}",
                                meta=dict(base_meta or {}, heading=heading)))
    return chunks


def chunk_input(filename: str, text: str, max_lines: int = 200) -> list[Chunk]:
    """Chunk a job input (diff, spec, notes). Markdown is split by heading; other text by line blocks."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    is_markdown = ext in ("md", "markdown", "txt", "")
    if is_markdown and re.search(r"^#{1,3}\s", text, re.M) and not text.lstrip().startswith("diff --git"):
        return [Chunk(id=f"input:{filename}#{c.id.split('#', 1)[1]}", heading=c.heading, text=c.text)
                for c in chunk_markdown(filename, text)]
    lines = text.splitlines()
    out = []
    for n, start in enumerate(range(0, max(1, len(lines)), max_lines)):
        piece = "\n".join(lines[start:start + max_lines]).strip()
        if piece:
            out.append(Chunk(id=f"input:{filename}#{n}", heading=filename, text=piece))
    return out
