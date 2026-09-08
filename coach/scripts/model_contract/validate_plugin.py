#!/usr/bin/env python3
"""Validate a model plugin manifest and optionally its runtime weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_ENTRYPOINTS = ("pose", "features", "narrative")


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return value


def _safe_relative_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must stay inside its configured root")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"{label} escapes its configured root")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_plugin(
    plugin_dir: Path,
    weights_root: Path | None = None,
) -> dict[str, Any]:
    plugin_dir = plugin_dir.resolve()
    manifest = _json_object(plugin_dir / "model_manifest.json")
    model_id = manifest.get("model_id")
    if not isinstance(model_id, str) or not MODEL_ID_PATTERN.fullmatch(model_id):
        raise ValueError("manifest model_id is invalid")
    if plugin_dir.name != model_id:
        raise ValueError("manifest model_id must match the plugin directory")

    entrypoints = manifest.get("entrypoints")
    if not isinstance(entrypoints, dict):
        raise ValueError("manifest entrypoints must be an object")
    for name in REQUIRED_ENTRYPOINTS:
        path = _safe_relative_path(
            plugin_dir,
            entrypoints.get(name),
            f"entrypoints.{name}",
        )
        if not path.is_file():
            raise ValueError(f"missing {name} entrypoint: {path}")

    source_files = manifest.get("source_files")
    if source_files is not None:
        if not isinstance(source_files, list) or not source_files:
            raise ValueError("manifest source_files must be a non-empty list")
        for index, value in enumerate(source_files):
            path = _safe_relative_path(
                plugin_dir,
                value,
                f"source_files[{index}]",
            )
            if not path.is_file():
                raise ValueError(f"missing source file: {path}")

    weights = manifest.get("weights")
    if not isinstance(weights, list) or not weights:
        raise ValueError("manifest weights must be a non-empty list")
    checked_weights = 0
    for index, item in enumerate(weights):
        if not isinstance(item, dict):
            raise ValueError(f"weights[{index}] must be an object")
        expected_hash = item.get("sha256")
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(
            expected_hash
        ):
            raise ValueError(f"weights[{index}].sha256 is invalid")
        if weights_root is not None:
            weight_path = _safe_relative_path(
                weights_root.resolve(),
                item.get("path"),
                f"weights[{index}].path",
            )
            if not weight_path.is_file():
                raise ValueError(f"missing model weight: {weight_path}")
            actual_hash = _sha256(weight_path)
            if actual_hash != expected_hash:
                raise ValueError(
                    f"model weight checksum mismatch: {weight_path}"
                )
            checked_weights += 1

    quality = manifest.get("quality")
    if not isinstance(quality, dict):
        raise ValueError("manifest quality must be an object")
    baseline_path = _safe_relative_path(
        plugin_dir,
        quality.get("baseline"),
        "quality.baseline",
    )
    baseline = _json_object(baseline_path)
    approval_status = baseline.get("approval_status")
    if approval_status not in {"pending_modeler_approval", "approved"}:
        raise ValueError("quality baseline approval_status is invalid")

    return {
        "status": "ok",
        "model_id": model_id,
        "approval_status": approval_status,
        "weight_count": len(weights),
        "checked_weight_count": checked_weights,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("--weights-root", type=Path)
    args = parser.parse_args()
    try:
        result = validate_plugin(args.plugin_dir, args.weights_root)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"MODEL_PLUGIN_INVALID={error}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
