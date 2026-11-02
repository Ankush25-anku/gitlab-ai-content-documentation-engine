"""Vector search over kb_chunks: pgvector on Postgres, in-process cosine on SQLite."""
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ai.retrieval.embeddings import cosine, embed_query
from backend.config import get_settings
from backend.database.models import KBChunk, KBDocument


@dataclass
class Hit:
    chunk_id: str
    document_id: str
    title: str
    heading: str
    text: str
    score: float
    updated_at: str
    stale: bool
    kind: str
    source_url: str | None


def _is_stale(updated: str) -> bool:
    try:
        d = datetime.fromisoformat(str(updated)).date()
    except ValueError:
        return False
    return (date.today() - d).days > get_settings().stale_after_days


def search(db: Session, query: str, top_k: int | None = None, product_area: str | None = None,
           exclude: set[str] | None = None, kinds: tuple[str, ...] = ("doc",)) -> list[Hit]:
    top_k = top_k or get_settings().retrieval_top_k
    exclude = exclude or set()
    qvec = embed_query(query)
    docs = {d.id: d for d in db.scalars(select(KBDocument)).all()}

    if not get_settings().is_sqlite:
        rows = db.execute(text(
            "select c.id, c.document_id, c.heading, c.text, 1 - (c.embedding <=> cast(:q as vector)) as score "
            "from kb_chunks c join kb_documents d on d.id = c.document_id "
            "where d.kind = any(:kinds) order by c.embedding <=> cast(:q as vector) limit :k"),
            {"q": str(qvec), "kinds": list(kinds), "k": top_k * 3}).all()
        scored = [(float(r.score), r.id, r.document_id, r.heading, r.text) for r in rows]
    else:
        scored = []
        for c in db.scalars(select(KBChunk)).all():
            d = docs.get(c.document_id)
            if d is None or d.kind not in kinds:
                continue
            scored.append((cosine(qvec, c.embedding), c.id, c.document_id, c.heading, c.text))
        scored.sort(reverse=True)

    hits: list[Hit] = []
    for score, cid, did, heading, body in scored:
        if cid in exclude:
            continue
        d = docs[did]
        boost = 0.05 if product_area and d.product_area.lower() == product_area.lower() else 0.0
        hits.append(Hit(chunk_id=cid, document_id=did, title=d.title, heading=heading, text=body,
                        score=round(score + boost, 4), updated_at=d.updated_at, stale=_is_stale(d.updated_at),
                        kind=d.kind, source_url=d.source_url))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
