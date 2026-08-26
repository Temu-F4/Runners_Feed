from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Iterable


CORPUS_PATH = Path(__file__).with_name("knowledge") / "carson_2024_forward_lean.json"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
LOGGER = logging.getLogger(__name__)


def _tokens(values: Iterable[str]) -> set[str]:
    return {
        token
        for value in values
        for token in TOKEN_PATTERN.findall(value.casefold())
        if len(token) > 1
    }


def load_corpus(path: Path = CORPUS_PATH) -> dict:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(corpus.get("source"), dict):
        raise ValueError("Evidence corpus must contain source metadata")
    if not isinstance(corpus.get("chunks"), list) or not corpus["chunks"]:
        raise ValueError("Evidence corpus must contain chunks")
    return corpus


def retrieve_for_metric(
    metric: dict,
    *,
    limit: int = 3,
    path: Path = CORPUS_PATH,
) -> list[dict]:
    metric_id = str(metric.get("id", ""))
    query_values = [metric_id, str(metric.get("label", ""))]
    query_values.extend(str(value) for value in metric.get("evidence_query", []))
    query_tokens = _tokens(query_values)

    corpus = load_corpus(path)
    ranked: list[tuple[int, dict]] = []
    for chunk in corpus["chunks"]:
        feature_ids = [str(value) for value in chunk.get("feature_ids", [])]
        searchable = [
            str(chunk.get("section", "")),
            str(chunk.get("text", "")),
            str(chunk.get("caveat", "")),
            *feature_ids,
            *(str(value) for value in chunk.get("keywords", [])),
        ]
        overlap = len(query_tokens & _tokens(searchable))
        score = overlap + (20 if metric_id in feature_ids else 0)
        if score > 0:
            ranked.append((score, chunk))

    ranked.sort(key=lambda item: (-item[0], item[1]["evidence_id"]))
    source = corpus["source"]
    return [
        {
            **chunk,
            "source": source,
            "retrieval_score": score,
            "matched_feature_id": metric_id,
        }
        for score, chunk in ranked[:limit]
    ]


def retrieve_evidence_keyword(
    metrics: list[dict],
    *,
    limit_per_metric: int = 3,
    path: Path = CORPUS_PATH,
) -> list[dict]:
    selected: dict[str, dict] = {}
    for metric in metrics:
        for evidence in retrieve_for_metric(
            metric,
            limit=limit_per_metric,
            path=path,
        ):
            evidence_id = evidence["evidence_id"]
            existing = selected.get(evidence_id)
            if existing is None:
                evidence["matched_feature_ids"] = [evidence.pop("matched_feature_id")]
                selected[evidence_id] = evidence
                continue
            matched = evidence["matched_feature_id"]
            if matched not in existing["matched_feature_ids"]:
                existing["matched_feature_ids"].append(matched)
            existing["retrieval_score"] = max(
                existing["retrieval_score"],
                evidence["retrieval_score"],
            )

    return sorted(
        selected.values(),
        key=lambda item: (-item["retrieval_score"], item["evidence_id"]),
    )


def retrieve_evidence(
    metrics: list[dict],
    *,
    limit_per_metric: int = 3,
    path: Path = CORPUS_PATH,
) -> list[dict]:
    vector_enabled = os.getenv("VECTOR_RAG_ENABLED", "false").casefold() == "true"
    if vector_enabled:
        try:
            from inference.vector_store import retrieve_evidence_vector

            results = retrieve_evidence_vector(
                metrics,
                limit_per_metric=limit_per_metric,
            )
            if results:
                return results
            LOGGER.warning("Vector retrieval returned no evidence; using JSON fallback")
        except Exception:
            LOGGER.exception("Vector retrieval failed; using JSON fallback")

    return retrieve_evidence_keyword(
        metrics,
        limit_per_metric=limit_per_metric,
        path=path,
    )
