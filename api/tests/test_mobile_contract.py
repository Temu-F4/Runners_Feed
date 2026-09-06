import json
import os
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.main import MobileJobRequest, _mobile_result, model_quality_health


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
