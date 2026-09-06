import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from output_validation import (
    ModelArtifactValidationError,
    validate_completed_artifacts,
)


class OutputValidationTests(TestCase):
    def _artifacts(self, root: Path) -> dict[str, Path]:
        payloads = {
            "details": {"video": {"frame_count": 1}},
            "predictions": {"frames": [{"people": []}]},
            "report": {"metrics": [], "features": {}},
        }
        artifacts = {}
        for name, payload in payloads.items():
            path = root / f"{name}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            artifacts[name] = path
        return artifacts

    def test_accepts_valid_completed_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            validate_completed_artifacts(self._artifacts(Path(directory)))

    def test_rejects_non_finite_result(self) -> None:
        with TemporaryDirectory() as directory:
            artifacts = self._artifacts(Path(directory))
            artifacts["report"].write_text(
                '{"metrics": [{"value": NaN}], "features": {}}',
                encoding="utf-8",
            )
            with self.assertRaises(ModelArtifactValidationError):
                validate_completed_artifacts(artifacts)

    def test_rejects_missing_report_contract_fields(self) -> None:
        with TemporaryDirectory() as directory:
            artifacts = self._artifacts(Path(directory))
            artifacts["report"].write_text("{}", encoding="utf-8")
            with self.assertRaises(ModelArtifactValidationError):
                validate_completed_artifacts(artifacts)
