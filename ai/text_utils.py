"""Small, dependency-free text helpers shared by agents, retrieval and evaluation."""
import re

from ai.schemas import Draft

CITATION_RE = re.compile(r"\[(S\d+)\]")
NEEDS_SOURCE_RE = re.compile(r"\[NEEDS SOURCE:[^\]]*\]")
INJECTION_RE = re.compile(
    r"(ignore (all |any )?(previous|prior|above) instructions|disregard (the|all) (rules|instructions)|"
    r"you are now|developer mode|system prompt|jailbreak|approve (this|the) draft|act as an?|"
    r"do not (cite|follow)|override (the )?(rules|instructions))", re.I)
WORD_RE = re.compile(r"[A-Za-z0-9_./:-]+")

STOPWORDS = set(
    "a an the and or but if then else of to in on for with by from as at is are was were be been being this that "
    "these those it its you your we our they their can will would should may might must do does did not no yes "
    "into over under about than so such via per each any all more most less new now also only use used using "
    "how what when where which who why".split()
)


def tokens(text: str) -> set[str]:
    """Content words (lower-cased, stopwords removed, citations stripped)."""
    text = CITATION_RE.sub(" ", text)
    return {w.lower().strip(".:,") for w in WORD_RE.findall(text)} - STOPWORDS - {""}


def overlap(claim: str, source: str) -> float:
    """Share of the claim's content words that appear in the source (0-1)."""
    c = tokens(claim)
    if not c:
        return 0.0
    return len(c & tokens(source)) / len(c)


def split_sentences(markdown: str) -> list[str]:
    """Split Markdown into checkable sentences. Code blocks and table rows are kept whole."""
    out: list[str] = []
    in_code = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith("|---") or set(line) <= set("|-: "):
            continue
        line = re.sub(r"^(#+|\d+\.|[-*])\s+", "", line)
        if line.startswith("|"):
            out.append(line)
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z`\[])", line)
        out.extend(p.strip() for p in parts if p.strip())
    return out


def plain_text(sentence: str) -> str:
    """A sentence without its citation markers, with spacing before punctuation fixed."""
    return re.sub(r"\s+([.,;:!?])", r"\1", CITATION_RE.sub("", sentence)).strip()


def citations(text: str) -> list[str]:
    return CITATION_RE.findall(text)


def is_checkable(sentence: str) -> bool:
    """A sentence worth fact-checking: not a pure marker, not a heading-like fragment."""
    stripped = NEEDS_SOURCE_RE.sub("", CITATION_RE.sub("", sentence)).strip(" .|")
    return len(stripped.split()) >= 5


def draft_to_markdown(draft: Draft, include_citations: bool = True) -> str:
    parts = [f"# {draft.title}", "", draft.summary, ""]
    for s in draft.sections:
        parts += [f"## {s.heading}", "", s.body_markdown.strip(), ""]
    md = "\n".join(parts).strip() + "\n"
    if not include_citations:
        md = re.sub(r"\s?\[S\d+\]", "", md)
    return md


def markdown_to_draft(md: str, base: Draft) -> Draft:
    """Parse a human-edited Markdown draft back into the Draft schema (keeps base metadata)."""
    from ai.schemas import Section

    title, summary_lines, sections = base.title, [], []
    current: list | None = None
    for line in md.splitlines():
        if line.startswith("# ") and not sections and current is None:
            title = line[2:].strip()
        elif line.startswith("## "):
            current = [line[3:].strip(), []]
            sections.append(current)
        elif current is None:
            summary_lines.append(line)
        else:
            current[1].append(line)
    built = []
    for heading, lines in sections:
        body = "\n".join(lines).strip()
        built.append(Section(heading=heading, body_markdown=body,
                             source_ids=sorted(set(citations(body)), key=lambda x: int(x[1:]))))
    return base.model_copy(update={"title": title, "summary": "\n".join(summary_lines).strip() or base.summary,
                                   "sections": built or base.sections, "change_log": ["Edited by a human reviewer"]})


def remove_sentence(draft: Draft, sentence: str) -> tuple[Draft, bool]:
    """Remove one claim (matched without its citations) from the draft."""
    def strip(body: str) -> tuple[str, bool]:
        for candidate in re.split(r"(?<=[.!?])\s+", body):
            if plain_text(candidate) == plain_text(sentence):
                return body.replace(candidate, "").replace("  ", " ").strip(), True
        for line in body.splitlines():
            if plain_text(re.sub(r"^(\d+\.|[-*])\s+", "", line.strip())) == plain_text(sentence):
                return "\n".join(x for x in body.splitlines() if x != line).strip(), True
        return body, False

    summary, found = strip(draft.summary)
    sections = []
    for s in draft.sections:
        body, hit = strip(s.body_markdown)
        found = found or hit
        sections.append(s.model_copy(update={"body_markdown": body or "[NEEDS SOURCE: section emptied by reviewer]"}))
    return draft.model_copy(update={"summary": summary, "sections": sections}), found


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", CITATION_RE.sub("", text)))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "untitled"
