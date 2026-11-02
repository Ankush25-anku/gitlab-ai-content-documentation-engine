"""Assembles the controlled source set for a job: job metadata (S0), job inputs, then KB chunks.

Every source gets a short citation id (S0, S1, ...) and keeps its stable chunk id, so a citation in
the draft always resolves to an exact chunk.
"""
from sqlalchemy.orm import Session

from ai.retrieval.chunker import chunk_input
from ai.retrieval.store import search
from ai.schemas import SourceRef


def build_sources(db: Session, job: dict, inputs: list[dict], exclude: set[str] | None = None,
                  top_k: int | None = None) -> tuple[list[SourceRef], list[str]]:
    """Return (sources, warnings)."""
    warnings: list[str] = []
    sources: list[SourceRef] = [SourceRef(
        id="S0", chunk_id="job:metadata", origin="input", title="Job brief",
        text=(f"Title: {job['title']}. Content type: {job['content_type']}. Audience: {job['audience']}. "
              f"Product area: {job['product_area']}. Target channel: {job['target_channel']}."),
    )]
    for inp in inputs:
        for c in chunk_input(inp["filename"], inp["text"]):
            sources.append(SourceRef(id=f"S{len(sources)}", chunk_id=c.id, origin="input",
                                     title=f"{inp['kind']}: {inp['filename']}", text=c.text))

    query = " ".join([job["title"], job["product_area"]] + [i["text"][:1500] for i in inputs])
    try:
        hits = search(db, query, top_k=top_k, product_area=job["product_area"], exclude=exclude)
    except Exception as exc:  # noqa: BLE001 - RETRIEVAL_FAILED is non-fatal by design
        hits = []
        warnings.append(f"RETRIEVAL_FAILED: {exc}. Continuing with job inputs only.")
    for h in hits:
        sources.append(SourceRef(id=f"S{len(sources)}", chunk_id=h.chunk_id, origin="kb",
                                 title=f"{h.title} > {h.heading}", text=h.text, score=h.score,
                                 updated_at=h.updated_at, stale=h.stale))
    if any(s.stale for s in sources):
        warnings.append("Some retrieved documentation is older than the freshness threshold.")
    return sources, warnings
