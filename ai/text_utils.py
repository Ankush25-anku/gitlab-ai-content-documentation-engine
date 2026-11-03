"""Small, dependency-free text helpers shared by agents, retrieval and evaluation."""
import re
from collections.abc import Collection

from pydantic import BaseModel

from ai.schemas import Draft

# Separators models put between ids inside one marker: "S1, S2", "S1,S2", "S1; S2", "S1 and S2", "S1, and S2", "S1 & S2".
_ID_SEP = r"(?:\s*[,;&]\s*(?:and\s+)?|\s+and\s+)"
_ID_LIST = rf"S\d+(?:{_ID_SEP}S\d+)*"
# One citation marker: canonical "[S1]" or a grouped "[S1, S2]". Every helper below accepts both.
CITATION_RE = re.compile(rf"\[\s*({_ID_LIST})\s*\]")
_PAREN_CITATION_RE = re.compile(rf"\(\s*({_ID_LIST})\s*\)")
_ID_RE = re.compile(r"S\d+")
_CODE_RE = re.compile(r"(```.*?```|`[^`\n]*`)", re.S)
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
    """Every cited id in order, including each id inside a grouped marker such as [S1, S2]."""
    return [sid for m in CITATION_RE.finditer(text) for sid in _ID_RE.findall(m.group(1))]


def strip_citations(text: str) -> str:
    """Remove citation markers (single or grouped) and the space before them."""
    return re.sub(r"\s?" + CITATION_RE.pattern, "", text)


def _canonical(match: re.Match) -> str:
    return " ".join(f"[{sid}]" for sid in dict.fromkeys(_ID_RE.findall(match.group(1))))


def normalise_citations(text: str, known_ids: Collection[str] | None = None) -> str:
    """Rewrite grouped citations into one id per bracket: "[S1, S2]", "[S1;S2]", "[S1 and S2]" -> "[S1] [S2]".

    "(S1)" and "(S1, S2)" are rewritten too, but only when every id in them is in `known_ids` (when given),
    so prose such as "object storage (S3)" is left alone. Code spans and fenced code blocks are never changed.
    """
    def paren(m: re.Match) -> str:
        ids = _ID_RE.findall(m.group(1))
        return _canonical(m) if known_ids is None or all(i in known_ids for i in ids) else m.group(0)

    parts = _CODE_RE.split(text)
    for i in range(0, len(parts), 2):  # even indexes are outside code
        parts[i] = _PAREN_CITATION_RE.sub(paren, CITATION_RE.sub(_canonical, parts[i]))
    return "".join(parts)


def normalise_source_ids(values: list[str]) -> list[str]:
    """Split entries such as "S1, S2" or "[S3]" into separate ids, keeping order and dropping duplicates."""
    out: list[str] = []
    for value in values:
        core = value.strip(" []()")
        out += _ID_RE.findall(core) if re.fullmatch(_ID_LIST, core) else [value]
    return list(dict.fromkeys(out))


def normalise_draft(draft: Draft, known_ids: Collection[str] | None = None) -> Draft:
    sections = [s.model_copy(update={"body_markdown": normalise_citations(s.body_markdown, known_ids),
                                     "source_ids": normalise_source_ids(s.source_ids)}) for s in draft.sections]
    return draft.model_copy(update={"summary": normalise_citations(draft.summary, known_ids), "sections": sections})


def normalise_output(obj, known_ids: Collection[str] | None = None):
    """Canonical citations in every Draft inside an agent output, and split ids in every `source_ids` list."""
    if isinstance(obj, Draft):
        return normalise_draft(obj, known_ids)
    if not isinstance(obj, BaseModel):
        return obj
    updates = {}
    for name in type(obj).model_fields:
        value = getattr(obj, name)
        if name == "source_ids" and isinstance(value, list):
            new = normalise_source_ids(value)
        elif isinstance(value, BaseModel):
            new = normalise_output(value, known_ids)
        elif isinstance(value, list) and value and isinstance(value[0], BaseModel):
            new = [normalise_output(v, known_ids) for v in value]
        else:
            continue
        if new != value:
            updates[name] = new
    return obj.model_copy(update=updates) if updates else obj


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
        md = strip_citations(md)
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
        # Human edits: canonicalise bracket groups only; "(S3)" typed by a person stays prose.
        body = normalise_citations("\n".join(lines).strip(), known_ids=())
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
