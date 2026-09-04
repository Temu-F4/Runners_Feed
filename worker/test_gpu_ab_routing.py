import unittest

from gpu_ab_routing import pipeline_command


class GpuAbRoutingTests(unittest.TestCase):
    def test_ordinary_and_cpu_cases_stay_local(self):
        environment = {"GPU_AB_ENABLED": "1"}
        for case_id in ("ordinary", "video_analysis_cpu_ab"):
            self.assertEqual(
                pipeline_command(case_id, ["runner"], environ=environment),
                ["env", "COACH_VIDEO_ANALYSIS_BACKEND=local", "runner"],
            )

    def test_gpu_case_is_explicitly_enabled(self):
        self.assertEqual(
            pipeline_command(
                "video_analysis_gpu_ab",
                ["runner"],
                environ={"GPU_AB_ENABLED": "1"},
            ),
            ["env", "COACH_VIDEO_ANALYSIS_BACKEND=runpod", "runner"],
        )
        with self.assertRaises(RuntimeError):
            pipeline_command("video_analysis_gpu_ab", ["runner"], environ={})

    def test_case_ids_must_be_distinct(self):
        with self.assertRaises(RuntimeError):
            pipeline_command(
                "same",
                ["runner"],
                environ={
                    "GPU_AB_CPU_CASE_ID": "same",
                    "GPU_AB_GPU_CASE_ID": "same",
                },
            )


if __name__ == "__main__":
    unittest.main()
