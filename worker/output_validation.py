import json
import math
from pathlib import Path


class ModelArtifactValidationError(ValueError):
    """The model completed but produced an unusable output contract."""


def _assert_finite_json(value: object, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ModelArtifactValidationError(f"non-finite value in {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_finite_json(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_finite_json(item, f"{path}[{index}]")


def validate_completed_artifacts(artifacts: dict[str, Path]) -> None:
    payloads: dict[str, dict] = {}
    for name in ("details", "predictions", "report"):
        try:
            payload = json.loads(artifacts[name].read_text(encoding="utf-8"))
        except (KeyError, OSError, json.JSONDecodeError) as error:
            raise ModelArtifactValidationError(
                f"invalid {name} JSON artifact"
            ) from error
        if not isinstance(payload, dict):
            raise ModelArtifactValidationError(
                f"{name} artifact must contain a JSON object"
            )
        _assert_finite_json(payload, name)
        payloads[name] = payload

    report = payloads["report"]
    if not isinstance(report.get("metrics"), list):
        raise ModelArtifactValidationError("report.metrics must be a list")
    if not isinstance(report.get("features"), dict):
        raise ModelArtifactValidationError("report.features must be an object")
