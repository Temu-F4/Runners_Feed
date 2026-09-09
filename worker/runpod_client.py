from __future__ import annotations

import json
import math
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "Runners-Feed-OCI-Dispatcher/1.0"

class RunPodError(RuntimeError):
    """Base error for the RunPod submit/poll contract."""

class RunPodTransientError(RunPodError):
    """A temporary transport or upstream failure that may be retried."""

class RunPodNotFoundError(RunPodError):
    """The accepted remote job no longer exists."""

class RunPodProtocolError(RunPodError):
    """The server response does not match the documented contract."""

class RunPodRemoteFailure(RunPodError):
    def __init__(self, error_code: str, error_message: str) -> None:
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(f"RunPod job failed ({error_code}): {error_message}")

class RunPodVideoAnalysisClient:
    def __init__(self, endpoint: str, token: str, *, timeout: float = 30, opener=urlopen) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username is not None or parsed.password is not None:
            raise ValueError("RunPod endpoint must be HTTPS")
        if token != token.strip() or len(token) < 24:
            raise ValueError("RunPod shared token must contain at least 24 characters")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("RunPod request timeout must be positive")
        base = endpoint.rstrip("/")
        self.endpoint = base if base.endswith("/v4/storage-video-analysis") else base + "/v4/storage-video-analysis"
        self.token = token
        self.timeout = timeout
        self.opener = opener

    def _request(self, request: Request, *, expected_status: int) -> dict:
        try:
            with self.opener(request, timeout=self.timeout, context=ssl.create_default_context()) as response:
                response_status = getattr(response, "status", None)
                if isinstance(response_status, int) and response_status != expected_status:
                    raise RunPodProtocolError(
                        f"RunPod returned HTTP {response_status}; expected {expected_status}"
                    )
                result = json.load(response)
        except HTTPError as error:
            if error.code == 404:
                raise RunPodNotFoundError("RunPod remote job was not found") from error
            if error.code in {408, 425, 429} or 500 <= error.code < 600:
                raise RunPodTransientError(f"RunPod temporary HTTP error {error.code}") from error
            raise RunPodProtocolError(f"RunPod rejected request with HTTP {error.code}") from error
        except (TimeoutError, URLError) as error:
            reason = getattr(error, "reason", error)
            raise RunPodTransientError(f"RunPod request failed: {reason}") from error
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            raise RunPodProtocolError("RunPod returned invalid JSON") from error
        if not isinstance(result, dict):
            raise RunPodProtocolError("RunPod response must be an object")
        return result

    @staticmethod
    def _validate_identity(result: dict, *, job_id: str, attempt_id: str) -> None:
        for key, expected in (("job_id", job_id), ("attempt_id", attempt_id)):
            if result.get(key) != expected:
                raise RunPodProtocolError(f"RunPod response mismatch: {key}")

    def submit(self, payload: dict) -> dict:
        request = Request(self.endpoint, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"), headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": USER_AGENT}, method="POST")
        result = self._request(request, expected_status=202)
        self._validate_identity(result, job_id=payload["job_id"], attempt_id=payload["attempt_id"])
        if result.get("status") != "accepted":
            raise RunPodProtocolError("RunPod submit response was not accepted")
        remote_job_id = result.get("remote_job_id")
        if not isinstance(remote_job_id, str) or not remote_job_id.strip():
            raise RunPodProtocolError("RunPod submit response has no remote_job_id")
        return result

    def poll(self, remote_job_id: str, *, job_id: str, attempt_id: str) -> dict:
        if not isinstance(remote_job_id, str) or not remote_job_id.strip():
            raise ValueError("remote_job_id is required")
        request = Request(f"{self.endpoint}/{quote(remote_job_id, safe='')}", headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json", "User-Agent": USER_AGENT}, method="GET")
        result = self._request(request, expected_status=200)
        self._validate_identity(result, job_id=job_id, attempt_id=attempt_id)
        status = result.get("status")
        if status not in {"queued", "running", "complete", "failed"}:
            raise RunPodProtocolError(f"Unknown RunPod job status: {status}")
        if status == "failed":
            code, message = result.get("error_code"), result.get("error_message")
            raise RunPodRemoteFailure(code if isinstance(code, str) and code else "RunPodRemoteFailure", message if isinstance(message, str) and message else "Remote analysis failed")
        if status == "complete":
            expected = f"jobs/{job_id}/video-analysis/{attempt_id}/pose_manifest.json"
            if result.get("manifest_object") != expected:
                raise RunPodProtocolError("RunPod response mismatch: manifest_object")
        return result

def client_from_environment() -> RunPodVideoAnalysisClient:
    return RunPodVideoAnalysisClient(os.environ["RUNPOD_VIDEO_ANALYSIS_ENDPOINT"], os.environ["RUNPOD_SHARED_TOKEN"], timeout=float(os.getenv("RUNPOD_REQUEST_TIMEOUT_SECONDS", "30")))
