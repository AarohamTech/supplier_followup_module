"""pgvector-backed knowledge store (Postgres only; no-op on SQLite).

Kept deliberately outside the SQLAlchemy ORM and managed with raw SQL so it
stays dialect-safe and needs no extra Python dependency: the `vector` column
type only exists on Postgres, so on SQLite (local dev) every function here is a
safe no-op and the app simply runs without semantic memory.

Schema (created on demand by `ensure_store`):

    knowledge_chunks(
        id, source_type, source_id, chunk_index,
        content, metadata jsonb, embedding vector(<EMBED_DIM>), created_at
    )  UNIQUE(source_type, source_id, chunk_index)

Distance is cosine (`<=>`); similarity returned to callers is `1 - distance`.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import engine

log = logging.getLogger(__name__)

_TABLE = "knowledge_chunks"
_ready: bool | None = None  # cache the ensure_store outcome


def is_postgres() -> bool:
    try:
        return engine.url.get_backend_name().startswith("postgresql")
    except Exception:  # noqa: BLE001
        return False


def available() -> bool:
    """True when the store has been successfully created on a Postgres backend."""
    return bool(is_postgres() and _ready)


def _vec_literal(embedding: list[float]) -> str:
    # pgvector accepts the textual form '[1,2,3]' cast to ::vector.
    return "[" + ",".join(f"{float(x):.7g}" for x in embedding) + "]"


def ensure_store() -> bool:
    """Create the extension, table and index if missing. Returns True on Postgres
    once ready; False (no-op) on SQLite or on failure."""
    global _ready
    if not is_postgres():
        _ready = False
        return False
    dim = int(settings.EMBED_DIM)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_TABLE} (
                        id BIGSERIAL PRIMARY KEY,
                        source_type VARCHAR(32) NOT NULL,
                        source_id BIGINT NOT NULL,
                        chunk_index INT NOT NULL DEFAULT 0,
                        content TEXT NOT NULL,
                        metadata JSONB,
                        embedding vector({dim}) NOT NULL,
                        created_at TIMESTAMP DEFAULT now(),
                        UNIQUE (source_type, source_id, chunk_index)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_{_TABLE}_source "
                    f"ON {_TABLE} (source_type, source_id)"
                )
            )
        # Vector ANN index is best-effort: hnsw (pgvector >=0.5), else skip and
        # fall back to an exact scan (fine for moderate corpus sizes).
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS ix_{_TABLE}_embedding "
                        f"ON {_TABLE} USING hnsw (embedding vector_cosine_ops)"
                    )
                )
        except Exception:  # noqa: BLE001
            log.info("hnsw index unavailable; using exact cosine scan for %s", _TABLE)
        _ready = True
        log.info("Vector store ready (%s, dim=%s)", _TABLE, dim)
        return True
    except Exception:  # noqa: BLE001
        log.exception("Vector store init failed; RAG features disabled")
        _ready = False
        return False


def upsert(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    chunks: list[str],
    embeddings: list[list[float]],
    metadata: dict[str, Any] | None = None,
) -> int:
    """Replace all chunks for (source_type, source_id) with the given ones."""
    if not available() or not chunks:
        return 0
    meta_json = json.dumps(metadata or {})
    try:
        db.execute(
            text(
                f"DELETE FROM {_TABLE} WHERE source_type = :st AND source_id = :sid"
            ),
            {"st": source_type, "sid": int(source_id)},
        )
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            db.execute(
                text(
                    f"""
                    INSERT INTO {_TABLE}
                        (source_type, source_id, chunk_index, content, metadata, embedding)
                    VALUES
                        (:st, :sid, :ci, :content, CAST(:meta AS jsonb), CAST(:emb AS vector))
                    """
                ),
                {
                    "st": source_type,
                    "sid": int(source_id),
                    "ci": idx,
                    "content": chunk,
                    "meta": meta_json,
                    "emb": _vec_literal(emb),
                },
            )
        db.commit()
        return len(chunks)
    except Exception:  # noqa: BLE001
        log.exception("vector_store.upsert failed for %s#%s", source_type, source_id)
        db.rollback()
        return 0


def indexed_source_ids(db: Session, source_type: str) -> set[int]:
    if not available():
        return set()
    try:
        rows = db.execute(
            text(
                f"SELECT DISTINCT source_id FROM {_TABLE} WHERE source_type = :st"
            ),
            {"st": source_type},
        ).all()
        return {int(r[0]) for r in rows}
    except Exception:  # noqa: BLE001
        log.exception("vector_store.indexed_source_ids failed")
        return set()


def search(
    db: Session,
    *,
    embedding: list[float],
    k: int = 5,
    source_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the k nearest chunks (cosine). Each row: content, source_type,
    source_id, metadata, similarity (0-1)."""
    if not available() or not embedding:
        return []
    params: dict[str, Any] = {"qvec": _vec_literal(embedding), "k": int(k)}
    filter_sql = ""
    if source_types:
        # Build a safe IN clause from a fixed allow-list of params.
        names = []
        for i, st in enumerate(source_types):
            key = f"st{i}"
            params[key] = st
            names.append(f":{key}")
        filter_sql = f"WHERE source_type IN ({', '.join(names)})"
    try:
        rows = db.execute(
            text(
                f"""
                SELECT content, source_type, source_id, metadata,
                       1 - (embedding <=> CAST(:qvec AS vector)) AS similarity
                FROM {_TABLE}
                {filter_sql}
                ORDER BY embedding <=> CAST(:qvec AS vector)
                LIMIT :k
                """
            ),
            params,
        ).all()
    except Exception:  # noqa: BLE001
        log.exception("vector_store.search failed")
        return []

    out: list[dict[str, Any]] = []
    for content, st, sid, meta, sim in rows:
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:  # noqa: BLE001
                meta = {}
        out.append(
            {
                "content": content,
                "source_type": st,
                "source_id": int(sid) if sid is not None else None,
                "metadata": meta or {},
                "similarity": round(float(sim), 4) if sim is not None else None,
            }
        )
    return out


def stats(db: Session) -> dict[str, Any]:
    if not available():
        return {"available": False, "total": 0, "by_source": {}}
    try:
        total = int(db.execute(text(f"SELECT count(*) FROM {_TABLE}")).scalar() or 0)
        rows = db.execute(
            text(f"SELECT source_type, count(*) FROM {_TABLE} GROUP BY source_type")
        ).all()
        return {
            "available": True,
            "total": total,
            "by_source": {st: int(c) for st, c in rows},
        }
    except Exception:  # noqa: BLE001
        log.exception("vector_store.stats failed")
        return {"available": False, "total": 0, "by_source": {}}
