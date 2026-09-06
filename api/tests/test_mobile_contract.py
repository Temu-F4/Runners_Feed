from unittest import TestCase
from uuid import uuid4

from app.main import MobileJobRequest, _mobile_result


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
