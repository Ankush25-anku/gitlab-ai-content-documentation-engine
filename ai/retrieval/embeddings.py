"""Embeddings.

- "hash": a deterministic hashed bag-of-words vector (offline, free, good enough for lexical
  retrieval in dev and CI).
- "gemini": Gemini embedding model through the REST API (production). Dimension must match the
  vector(768) column in the migration.
"""
import hashlib
import math

import httpx

from ai.text_utils import tokens
from backend.config import get_settings


def _hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    words = list(tokens(text))
    grams = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _gemini_embed(texts: list[str], task: str) -> list[list[float]]:
    s = get_settings()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{s.embedding_model}:batchEmbedContents"
    body = {"requests": [{"model": f"models/{s.embedding_model}", "content": {"parts": [{"text": t[:8000]}]},
                          "taskType": task, "outputDimensionality": s.embedding_dim} for t in texts]}
    resp = httpx.post(url, json=body, headers={"x-goog-api-key": s.gemini_api_key}, timeout=60)
    resp.raise_for_status()
    vectors = [e["values"] for e in resp.json()["embeddings"]]
    out = []
    for v in vectors:  # normalise (truncated Gemini vectors are not unit length)
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def embed_documents(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if s.embedding_provider == "gemini":
        out: list[list[float]] = []
        for i in range(0, len(texts), 50):
            out += _gemini_embed(texts[i:i + 50], "RETRIEVAL_DOCUMENT")
        return out
    return [_hash_embed(t, s.embedding_dim) for t in texts]


def embed_query(text: str) -> list[float]:
    s = get_settings()
    if s.embedding_provider == "gemini":
        return _gemini_embed([text], "RETRIEVAL_QUERY")[0]
    return _hash_embed(text, s.embedding_dim)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
