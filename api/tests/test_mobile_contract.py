import json
import os
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.main import MobileJobRequest, _mobile_result, _mobile_stage, model_quality_health


class MobileContractTests(TestCase):
    def test_mobile_job_request_uses_design_contract_names(self) -> None:
        payload = MobileJobRequest(
            inputObjectName="uploads/0123456789abcdef0123456789abcdef.mp4",
            userHeightCm=178,
        )
        self.assertEqual(payload.input_object_name, "uploads/0123456789abcdef0123456789abcdef.mp4")
        self.assertEqual(payload.user_height_cm, 178)

    def test_mobile_result_does_not_invent_missing_quality_fields(self) -> None:
        job = {
            "job_id": uuid4(),
            "created_at": "2026-09-07T00:00:00Z",
            "completed_at": "2026-09-07T00:01:00Z",
        }
        report = {
            "video": {"frame_count": 12},
            "tracking": {"tracked_frames": 10, "total_frames": 12},
            "metrics": [
                {
                    "id": "feature1",
                    "label": "골반 수직진동",
                    "value": 0.1,
                    "unit": "ratio",
                }
            ],
            "features": {"feature1": {}},
            "narrative": {"status": "disabled"},
            "evidence": [],
        }

        result = _mobile_result(job, report)

        self.assertEqual(result["features"][0]["verdict"], "review")
        self.assertIsNone(result["features"][0]["referenceRange"])
        self.assertEqual(result["features"][0]["confidenceLevel"], "excluded")
        self.assertEqual(result["narrative"]["status"], "unavailable")

    @patch("app.main.get_job_stages")
    def test_mobile_failed_stage_matches_the_actual_failed_pipeline_stage(self, stages) -> None:
        stages.return_value = [
            {"stage_key": "input_download", "status": "SUCCESS"},
            {"stage_key": "video_analysis", "status": "SUCCESS"},
            {"stage_key": "feature_extract", "status": "FAILED"},
        ]

        stage, progress = _mobile_stage({"job_id": uuid4(), "status": "FAILED"})

        self.assertEqual(stage, "features")
        self.assertIsNone(progress)

    def test_mobile_result_preserves_representative_value_and_maps_evidence(self) -> None:
        job = {
            "job_id": uuid4(),
            "created_at": "2026-09-07T00:00:00Z",
            "completed_at": "2026-09-07T00:01:00Z",
        }
        report = {
            "metrics": [{"id": "feature1", "label": "몸통 기울기", "value": 12, "unit": "°"}],
            "features": {
                "feature1": {
                    "priority": 1,
                    "verdict": "improve",
                    "reference_range": {"kind": "recommended", "min": 4, "max": 8, "unit": "°", "criterion_version": "v1", "evidence_ids": ["paper-1"]},
                    "series": [{"frame_index": 1, "timestamp_ms": 100, "value": 11}, {"frame_index": 2, "timestamp_ms": 200, "value": 13}],
                    "confidence_pct": 91,
                    "confidence_level": "high",
                    "interpretation": "범위보다 큽니다.",
                    "coaching_action": "상체를 조금 더 세워 보세요.",
                    "evidence_ids": ["paper-1"],
                }
            },
            "evidence": [{
                "evidence_id": "paper-1",
                "title": "Running form paper",
                "authors": "Author",
                "year": 2024,
                "doi": "10.0000/example",
                "page": 3,
                "section": "Methods",
                "excerpt_summary": "Reference summary",
                "caveat": "Small sample",
            }],
            "narrative": {
                "status": "success",
                "priority_actions": [{"feature_id": "feature1", "text": "상체를 세워 보세요."}],
                "maintain_actions": [],
            },
        }

        result = _mobile_result(job, report)

        self.assertEqual(result["features"][0]["representativeValue"], 12)
        self.assertEqual(result["features"][0]["series"][1]["value"], 13)
        self.assertEqual(result["features"][0]["referenceRange"]["criterionVersion"], "v1")
        self.assertEqual(result["evidence"][0]["evidenceId"], "paper-1")
        self.assertEqual(result["narrative"]["priorityActions"][0]["featureId"], "feature1")

    @patch("app.main.get_model_quality_summary")
    def test_quality_health_accepts_initial_sample_for_current_release(
        self,
        summary,
    ) -> None:
        summary.return_value = {
            "completed_count": 1,
            "success_count": 1,
            "failure_count": 0,
            "invalid_result_count": 0,
            "stale_processing_count": 0,
            "average_processing_seconds": 12,
        }
        with patch.dict(
            os.environ,
            {"MODEL_RELEASE": "sha-test", "COACH_MODEL_ID": "model-test"},
        ):
            response = model_quality_health()

        self.assertEqual(response["status"], "insufficient_sample")
        self.assertEqual(response["modelRelease"], "sha-test")
        summary.assert_called_once_with(
            window_minutes=60,
            max_processing_seconds=3600,
            model_id="model-test",
            model_release="sha-test",
        )

    @patch("app.main.get_model_quality_summary")
    def test_invalid_artifact_requires_rollback_before_minimum_sample(
        self,
        summary,
    ) -> None:
        summary.return_value = {
            "completed_count": 1,
            "success_count": 0,
            "failure_count": 1,
            "invalid_result_count": 1,
            "stale_processing_count": 0,
            "average_processing_seconds": 12,
        }
        with patch.dict(os.environ, {"MODEL_RELEASE": "sha-test"}):
            response = model_quality_health()

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "rollback_required")
        self.assertIn(
            "invalid_result_artifact_detected",
            payload["rollbackConditionsTriggered"],
        )
