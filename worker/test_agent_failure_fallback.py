import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class AgentFailureFallbackTests(unittest.TestCase):
    def test_llm_failure_writes_unavailable_narrative_and_exits_successfully(self) -> None:
        false_command = shutil.which("false")
        self.assertIsNotNone(false_command)
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run" / "fixture"
            (run_dir / "outputs").mkdir(parents=True)
            env = {
                **os.environ,
                "WORKSPACE_ROOT": directory,
                "PYTHON_BIN": sys.executable,
                "COACH_AGENT_ENTRYPOINT": false_command or "/usr/bin/false",
            }
            completed = subprocess.run(
                ["bash", str(repo / "coach/scripts/Agent/agent.sh"), "fixture"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads((run_dir / "outputs/running_report.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "unavailable")
            self.assertEqual(payload["error_code"], "llm_request_failed")


if __name__ == "__main__":
    unittest.main()
