import os
import unittest
from unittest.mock import patch

from validate_runpod_config import main


class RunPodStartupValidationTests(unittest.TestCase):
    def test_missing_configuration_fails_before_worker_start(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(), 1)

    def test_valid_configuration_passes(self):
        with patch.dict(os.environ, {
            "RUNPOD_VIDEO_ANALYSIS_ENDPOINT": "https://pod.example",
            "RUNPOD_SHARED_TOKEN": "x" * 24,
        }, clear=True):
            self.assertEqual(main(), 0)


if __name__ == "__main__":
    unittest.main()
