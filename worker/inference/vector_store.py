from __future__ import annotations

import argparse
import os
import uuid
from typing import Iterable

import psycopg
from langchain_ollama import OllamaEmbeddings
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from inference.evidence import load_corpus


EMBEDDING_DIMENSIONS = 768
CREATE_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector"
CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS paper_chunks (
    id UUID PRIMARY KEY,
    source_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    doi TEXT NOT NULL,
    page_number INTEGER,
    section TEXT,
    content TEXT NOT NULL,
    caveat TEXT NOT NULL DEFAULT '',
    feature_ids TEXT[] NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{{}}',
    embedding VECTOR({EMBEDDING_DIMENSIONS}) NOT NULL,
    embedding_model TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
CREATE_SOURCE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS paper_chunks_source_idx
ON paper_chunks (source_id)
"""
CREATE_FEATURE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS paper_chunks_feature_ids_idx
ON paper_chunks USING GIN (feature_ids)
"""
CREATE_VECTOR_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS paper_chunks_embedding_hnsw_idx
ON paper_chunks USING hnsw (embedding vector_cosine_ops)
"""


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def _embedding_model() -> str:
    return os.getenv("OLLAMA_EMBEDDING_MODEL", "embeddinggemma")


def _embedding_client() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=_embedding_model(),
        base_url=os.getenv(
            "OLLAMA_EMBEDDING_BASE_URL",
            "http://ollama:11434",
        ),
    )


def _validate_embedding(embedding: Iterable[float]) -> list[float]:
    values = list(embedding)
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSIONS}-dimensional embedding, "
            f"received {len(values)}"
        )
    return values


def initialize_vector_schema() -> None:
    with psycopg.connect(_database_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CREATE_EXTENSION_SQL)
            cursor.execute(CREATE_TABLE_SQL)
            cursor.execute(CREATE_SOURCE_INDEX_SQL)
            cursor.execute(CREATE_FEATURE_INDEX_SQL)
            cursor.execute(CREATE_VECTOR_INDEX_SQL)


def _document_text(source: dict, chunk: dict) -> str:
    return "\n".join(
        value
        for value in (
            f"Title: {source['title']}",
            f"Section: {chunk.get('section', '')}",
            f"Features: {', '.join(chunk.get('feature_ids', []))}",
            str(chunk.get("text", "")),
            f"Caveat: {chunk.get('caveat', '')}",
        )
        if value
    )


def ingest_corpus() -> dict[str, object]:
    corpus = load_corpus()
    source = corpus["source"]
    chunks = corpus["chunks"]
    client = _embedding_client()
    embeddings = client.embed_documents(
        [_document_text(source, chunk) for chunk in chunks]
    )
    if len(embeddings) != len(chunks):
        raise ValueError("Embedding response count does not match corpus chunk count")

    initialize_vector_schema()
    evidence_ids = [str(chunk["evidence_id"]) for chunk in chunks]
    with psycopg.connect(_database_url()) as connection:
        register_vector(connection)
        with connection.cursor() as cursor:
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                evidence_id = str(chunk["evidence_id"])
                chunk_id = uuid.uuid5(uuid.NAMESPACE_URL, evidence_id)
                metadata = {
                    "keywords": chunk.get("keywords", []),
                    "source": source,
                }
                cursor.execute(
                    """
                    INSERT INTO paper_chunks (
                        id, source_id, evidence_id, title, doi,
                        page_number, section, content, caveat,
                        feature_ids, metadata, embedding, embedding_model
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (evidence_id) DO UPDATE SET
                        source_id = EXCLUDED.source_id,
                        title = EXCLUDED.title,
                        doi = EXCLUDED.doi,
                        page_number = EXCLUDED.page_number,
                        section = EXCLUDED.section,
                        content = EXCLUDED.content,
                        caveat = EXCLUDED.caveat,
                        feature_ids = EXCLUDED.feature_ids,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding,
                        embedding_model = EXCLUDED.embedding_model,
                        updated_at = NOW()
                    """,
                    (
                        chunk_id,
                        source["source_id"],
                        evidence_id,
                        source["title"],
                        source["doi"],
                        chunk.get("page"),
                        chunk.get("section"),
                        chunk["text"],
                        chunk.get("caveat", ""),
                        chunk.get("feature_ids", []),
                        Jsonb(metadata),
                        Vector(_validate_embedding(embedding)),
                        _embedding_model(),
                    ),
                )
            cursor.execute(
                """
                DELETE FROM paper_chunks
                WHERE source_id = %s
                  AND NOT (evidence_id = ANY(%s))
                """,
                (source["source_id"], evidence_ids),
            )

    return {
        "source_id": source["source_id"],
        "embedding_model": _embedding_model(),
        "chunk_count": len(chunks),
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
    }


def _query_text(metric: dict) -> str:
    values = [
        str(metric.get("id", "")),
        str(metric.get("label", "")),
        *(str(value) for value in metric.get("evidence_query", [])),
    ]
    return "Running biomechanics evidence for: " + "; ".join(values)


def retrieve_evidence_vector(
    metrics: list[dict],
    *,
    limit_per_metric: int = 3,
) -> list[dict]:
    if not metrics:
        return []

    client = _embedding_client()
    query_embeddings = client.embed_documents([_query_text(metric) for metric in metrics])
    if len(query_embeddings) != len(metrics):
        raise ValueError("Embedding response count does not match metric count")

    selected: dict[str, dict] = {}
    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        register_vector(connection)
        with connection.cursor() as cursor:
            for metric, embedding in zip(metrics, query_embeddings, strict=True):
                metric_id = str(metric.get("id", ""))
                cursor.execute(
                    """
                    SELECT evidence_id,
                           page_number,
                           section,
                           content,
                           caveat,
                           feature_ids,
                           metadata,
                           1 - (embedding <=> %s) AS similarity
                    FROM paper_chunks
                    WHERE %s = ANY(feature_ids)
                      AND embedding_model = %s
                    ORDER BY embedding <=> %s
                    LIMIT %s
                    """,
                    (
                        Vector(_validate_embedding(embedding)),
                        metric_id,
                        _embedding_model(),
                        Vector(_validate_embedding(embedding)),
                        limit_per_metric,
                    ),
                )
                for row in cursor.fetchall():
                    evidence_id = row["evidence_id"]
                    existing = selected.get(evidence_id)
                    if existing is None:
                        metadata = row["metadata"] or {}
                        selected[evidence_id] = {
                            "evidence_id": evidence_id,
                            "page": row["page_number"],
                            "section": row["section"],
                            "feature_ids": row["feature_ids"],
                            "keywords": metadata.get("keywords", []),
                            "text": row["content"],
                            "caveat": row["caveat"],
                            "source": metadata.get("source", {}),
                            "retrieval_score": round(float(row["similarity"]), 6),
                            "retrieval_method": "pgvector_cosine",
                            "matched_feature_ids": [metric_id],
                        }
                        continue
                    if metric_id not in existing["matched_feature_ids"]:
                        existing["matched_feature_ids"].append(metric_id)
                    existing["retrieval_score"] = max(
                        existing["retrieval_score"],
                        round(float(row["similarity"]), 6),
                    )

    return sorted(
        selected.values(),
        key=lambda item: (-item["retrieval_score"], item["evidence_id"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "ingest"))
    args = parser.parse_args()
    if args.command == "init":
        initialize_vector_schema()
        print("VECTOR_SCHEMA=PASS")
        return
    result = ingest_corpus()
    print(
        "VECTOR_INGEST=PASS "
        f"source={result['source_id']} "
        f"chunks={result['chunk_count']} "
        f"model={result['embedding_model']} "
        f"dimensions={result['embedding_dimensions']}"
    )


if __name__ == "__main__":
    main()
