"""Ingest the knowledge base (docs, style guide, templates) into kb_documents + kb_chunks.

Usage:  python -m ai.retrieval.ingest            # ingests data/sample_docs and data/style_guides
        python -m ai.retrieval.ingest --reset    # wipes the KB first
"""
import argparse
from datetime import date
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ai.retrieval.chunker import chunk_markdown, parse_front_matter
from ai.retrieval.embeddings import embed_documents
from backend.database.models import KBChunk, KBDocument

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FOLDERS = {"sample_docs": "doc", "style_guides": "style_guide", "content_templates": "template"}


def ingest_file(db: Session, path: Path, kind: str) -> int:
    front, body = parse_front_matter(path.read_text(encoding="utf-8"))
    slug = front.get("slug") or path.stem
    doc = db.get(KBDocument, slug) or KBDocument(id=slug)
    doc.title = front.get("title", path.stem.replace("-", " ").title())
    doc.source_url = front.get("source_url")
    doc.product_area = front.get("product_area", "general")
    doc.content_type = front.get("content_type", "docs_page")
    doc.kind = kind
    doc.owner = front.get("owner")
    doc.updated_at = str(front.get("updated_at", date.today().isoformat()))
    db.merge(doc)
    db.execute(delete(KBChunk).where(KBChunk.document_id == slug))
    chunks = chunk_markdown(slug, body, {"product_area": doc.product_area, "kind": kind})
    vectors = embed_documents([c.text for c in chunks])
    for c, v in zip(chunks, vectors):
        db.add(KBChunk(id=c.id, document_id=slug, heading=c.heading, text=c.text, embedding=v, meta=c.meta))
    return len(chunks)


def ingest_all(db: Session, reset: bool = False) -> dict:
    if reset:
        db.execute(delete(KBChunk))
        db.execute(delete(KBDocument))
    stats = {"documents": 0, "chunks": 0}
    for folder, kind in FOLDERS.items():
        for path in sorted((DATA_DIR / folder).glob("*.md")):
            stats["chunks"] += ingest_file(db, path, kind)
            stats["documents"] += 1
    db.commit()
    return stats


if __name__ == "__main__":
    from backend.database.session import init_db, new_session

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    init_db()
    with new_session() as session:
        print(ingest_all(session, reset=args.reset))
