"""Embeddings gateway — the single place that turns text into vectors.

Mirrors `ai_service.py`: wraps an OpenAI-compatible embeddings endpoint (NVIDIA
NIM by default, reusing the same API key) and is safe by default — if
`RAG_ENABLED` is false or the key is missing, callers get a clear
`EmbeddingsDisabledError` and the app keeps running SQL-only.

NVIDIA's `nv-embedqa-*` family needs an `input_type` hint:
  - "passage" when embedding stored documents (indexing)
  - "query"   when embedding a search string
and a `truncate` policy so inputs over the model's token limit don't error.

Used by:
  - services/knowledge_indexer.py → embed mails/replies for the vector store
  - services/ai_tools_service.py   → embed the agent's search query (RAG tool)
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from ..core.config import settings

log = logging.getLogger(__name__)


class EmbeddingsDisabledError(RuntimeError):
    """Raised when an embedding call is attempted while RAG is disabled."""


def is_enabled() -> bool:
    return bool(settings.RAG_ENABLED and settings.embed_api_key)


def dim() -> int:
    return int(settings.EMBED_DIM)


@lru_cache(maxsize=1)
def _client():
    """Lazily build (and cache) the OpenAI-compatible embeddings client."""
    from openai import OpenAI  # imported lazily so the app boots without the SDK

    return OpenAI(
        base_url=settings.EMBED_BASE_URL,
        api_key=settings.embed_api_key,
        timeout=settings.EMBED_TIMEOUT_SECONDS,
        max_retries=0,  # fail fast — indexing/search degrade gracefully
    )


def _extra_body(input_type: str) -> dict[str, Any] | None:
    if not settings.EMBED_USES_INPUT_TYPE:
        return None
    # truncate=END keeps long bodies under the model's token cap instead of 400ing.
    return {"input_type": input_type, "truncate": "END"}


def _embed(texts: list[str], *, input_type: str) -> list[list[float]]:
    if not is_enabled():
        raise EmbeddingsDisabledError(
            "RAG is disabled (set RAG_ENABLED=true and provide an embedding key)."
        )
    cleaned = [(t or "").strip() or " " for t in texts]
    resp = _client().embeddings.create(
        model=settings.EMBED_MODEL,
        input=cleaned,
        encoding_format="float",
        extra_body=_extra_body(input_type),
    )
    # The SDK returns items in input order, but sort by index to be safe.
    items = sorted(resp.data, key=lambda d: d.index)
    return [list(item.embedding) for item in items]


# ── Public API ───────────────────────────────────────────────────────────────
def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed stored documents (passages) for indexing."""
    if not texts:
        return []
    return _embed(texts, input_type="passage")


def embed_query(text: str) -> list[float]:
    """Embed a single search query."""
    out = _embed([text], input_type="query")
    return out[0] if out else []


def health() -> dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "model": settings.EMBED_MODEL,
        "dim": settings.EMBED_DIM,
        "base_url": settings.EMBED_BASE_URL,
        "has_key": bool(settings.embed_api_key),
    }
