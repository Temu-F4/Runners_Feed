from __future__ import annotations

import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class RunPodVideoAnalysisClient:
    def __init__(self, endpoint: str, token: str, *, timeout: float = 3700, opener=urlopen) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("RunPod endpoint must be HTTPS")
        if len(token) < 24:
            raise ValueError("RunPod shared token must contain at least 24 characters")
        self.endpoint = endpoint.rstrip("/") + "/v4/storage-video-analysis"
        self.token = token
        self.timeout = timeout
        self.opener = opener

    def submit(self, payload: dict) -> dict:
        request = Request(
            self.endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout, context=ssl.create_default_context()) as response:
                result = json.load(response)
        except HTTPError as error:
            body = error.read(1000).decode("utf-8", errors="replace")
            raise RuntimeError(f"RunPod rejected request ({error.code}): {body}") from error
        except URLError as error:
            raise RuntimeError(f"RunPod request failed: {error.reason}") from error
        if not isinstance(result, dict) or result.get("status") != "complete":
            raise RuntimeError("RunPod returned an incomplete response")
        for key in ("job_id", "attempt_id"):
            if result.get(key) != payload[key]:
                raise RuntimeError(f"RunPod response mismatch: {key}")
        expected = payload["result_prefix"] + "/pose_manifest.json"
        if result.get("manifest_object") != expected:
            raise RuntimeError("RunPod response mismatch: manifest_object")
        return result


def client_from_environment() -> RunPodVideoAnalysisClient:
    return RunPodVideoAnalysisClient(
        os.environ["RUNPOD_VIDEO_ANALYSIS_ENDPOINT"],
        os.environ["RUNPOD_SHARED_TOKEN"],
        timeout=float(os.getenv("RUNPOD_REQUEST_TIMEOUT", "3700")),
    )
