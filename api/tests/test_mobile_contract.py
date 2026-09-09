import json
import os
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.main import MobileJobRequest, _mobile_exercise_video, _mobile_result, _mobile_signals, _mobile_stage, model_quality_health


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
        self.assertEqual(result["runMetrics"]["pacePerKm"], None)

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

    @patch("app.main.get_job_stages")
    def test_processing_without_remote_running_stage_is_waiting(self, stages) -> None:
        stages.return_value = [
            {"stage_key": "input_download", "status": "PENDING"},
            {"stage_key": "video_analysis", "status": "PENDING"},
        ]
        stage, progress = _mobile_stage({"job_id": uuid4(), "status": "PROCESSING"})
        self.assertEqual(stage, "queue")
        self.assertIsNone(progress)

    @patch("app.main.get_job_stages")
    def test_remote_running_stage_is_movement_analysis_without_fake_progress(self, stages) -> None:
        stages.return_value = [
            {"stage_key": "input_download", "status": "PENDING"},
            {"stage_key": "video_analysis", "status": "RUNNING"},
        ]
        stage, progress = _mobile_stage({"job_id": uuid4(), "status": "PROCESSING"})
        self.assertEqual(stage, "keypoints")
        self.assertIsNone(progress)

    def test_success_is_complete(self) -> None:
        self.assertEqual(
            _mobile_stage({"job_id": uuid4(), "status": "SUCCESS"}),
            ("result", 100.0),
        )

    @patch("app.main.get_job_stages")
    def test_result_upload_is_still_result_preparation_until_job_succeeds(self, stages) -> None:
        stages.return_value = [
            {"stage_key": "video_analysis", "status": "SUCCESS"},
            {"stage_key": "result_upload", "status": "RUNNING"},
        ]
        self.assertEqual(
            _mobile_stage({"job_id": uuid4(), "status": "PROCESSING"}),
            ("validation", None),
        )

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
                    "score": 42.5,
                    "score_method": "reference-band frame compliance",
                    "denominator_policy": "all_frames",
                    "good_frame_count": 1,
                    "evaluated_frame_count": 2,
                    "source_frame_count": 3,
                    "evaluation_coverage_pct": 66.67,
                    "confidence_assumed": True,
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
                "error_code": "should_not_be_used",
                "priority_actions": [{"feature_id": "feature1", "text": "상체를 세워 보세요."}],
                "maintain_actions": [],
                "exercise_videos": [{
                    "id": "trunk_form", "title": "몸통 자세 점검",
                    "url": "https://www.youtube.com/watch?v=gYajoeR_UF8",
                    "feature": "Trunk flexion angle",
                }],
            },
        }

        result = _mobile_result(job, report)

        self.assertEqual(result["features"][0]["representativeValue"], 12)
        self.assertEqual(result["features"][0]["series"][1]["value"], 13)
        self.assertEqual(result["features"][0]["referenceRange"]["criterionVersion"], "v1")
        self.assertEqual(result["features"][0]["score"], 42.5)
        self.assertEqual(
            result["features"][0]["scoreMethod"],
            "reference-band frame compliance",
        )
        self.assertTrue(result["features"][0]["confidenceAssumed"])
        self.assertEqual(result["features"][0]["denominatorPolicy"], "all_frames")
        self.assertEqual(result["evidence"][0]["evidenceId"], "paper-1")
        self.assertEqual(result["narrative"]["priorityActions"][0]["featureId"], "feature1")
        self.assertEqual(result["narrative"]["exerciseVideos"][0]["id"], "trunk_form")
        self.assertEqual(result["narrative"]["exerciseVideos"][0]["featureId"], "feature3")
        self.assertIsNone(result["narrative"]["errorCode"])
        home_signal = _mobile_signals(result["features"])[0]
        self.assertEqual(home_signal["featureId"], "feature1")
        self.assertEqual(home_signal["value"], result["features"][0]["representativeValue"])
        self.assertEqual(home_signal["score"], result["features"][0]["score"])
        self.assertTrue(home_signal["confidenceAssumed"])

    def test_mobile_result_maps_optional_run_metrics(self) -> None:
        job = {
            "job_id": uuid4(),
            "created_at": "2026-09-07T00:00:00Z",
            "completed_at": "2026-09-07T00:01:00Z",
        }
        report = {
            "metrics": [],
            "features": {},
            "narrative": {"status": "disabled"},
            "run_metrics": {"pace_per_km": "4:25", "cadence_spm": 181},
        }

        result = _mobile_result(job, report)

        self.assertEqual(result["runMetrics"]["pacePerKm"], "4:25")
        self.assertEqual(result["runMetrics"]["cadenceSpm"], 181)

    def test_mobile_result_preserves_unavailable_feature(self) -> None:
        job = {"job_id": uuid4(), "created_at": "now", "completed_at": "now"}
        result = _mobile_result(job, {
            "metrics": [{"id": "feature1", "label": "골반 수직 진폭", "value": None, "unit": "ratio"}],
            "features": {
                "feature1": {
                    "verdict": "unavailable",
                    "representative_value": None,
                    "interpretation": "접지 구간이 검출되지 않았습니다.",
                }
            },
            "narrative": {"status": "unavailable"},
        })

        feature = result["features"][0]
        self.assertEqual(feature["verdict"], "unavailable")
        self.assertIsNone(feature["representativeValue"])
        self.assertEqual(feature["interpretation"], "접지 구간이 검출되지 않았습니다.")

    def test_mobile_result_preserves_unavailable_narrative_error_code(self) -> None:
        job = {"job_id": uuid4(), "created_at": "now", "completed_at": "now"}
        result = _mobile_result(job, {
            "metrics": [], "features": {},
            "narrative": {"status": "unavailable", "error_code": "llm_request_failed"},
        })
        self.assertEqual(result["narrative"]["status"], "unavailable")
        self.assertEqual(result["narrative"]["errorCode"], "llm_request_failed")

    def test_mobile_exercise_video_rejects_non_youtube_or_malformed_urls(self) -> None:
        for url in (
            "http://www.youtube.com/watch?v=unsafe",
            "https://youtube.com/watch?v=wrong-host",
            "https://www.youtube.com/embed/not-watch",
            "https://www.youtube.com/watch",
        ):
            with self.subTest(url=url):
                self.assertIsNone(_mobile_exercise_video({
                    "id": "video", "title": "exercise", "url": url,
                }))

    def test_mobile_result_maps_runtime_metadata_without_persisting_signed_media(self) -> None:
        job = {"job_id": uuid4(), "created_at": "now", "completed_at": "now"}
        result = _mobile_result(job, {
            "metrics": [], "features": {}, "narrative": {"status": "disabled"},
            "runtime_metadata": {
                "prompt_version": "v2", "model": "model", "validator_version": "validator",
                "input_tokens": 12, "output_tokens": 8,
            },
        })
        self.assertIsNone(result["media"])
        self.assertEqual(result["runtimeMetadata"]["promptVersion"], "v2")
        self.assertEqual(result["runtimeMetadata"]["validatorVersion"], "validator")

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
