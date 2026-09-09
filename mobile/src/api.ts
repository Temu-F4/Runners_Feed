import * as FileSystem from "expo-file-system/legacy";

import { API_BASE_URL, DEMO_FIXTURES_ENABLED, DEMO_MODE } from "./config";
import type {
  ActiveAnalysisJob,
  AnalysisResult,
  DashboardResponse,
  MobileProfile,
} from "./contracts";
import { demoDashboard, demoJob, demoResult } from "./demo-results";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token: string | null,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : `API request failed (${response.status})`;
    throw new ApiError(detail, response.status);
  }
  return payload as T;
}

export async function createGuestSession() {
  return request<{
    accessToken: string;
    tokenType: "Bearer";
    sessionType: "guest";
    expiresAt: string;
  }>("/mobile/v1/sessions/guest", null, { method: "POST" });
}

export function getMe(token: string) {
  return request<MobileProfile>("/mobile/v1/me", token);
}

export async function getDashboard(token: string): Promise<DashboardResponse> {
  if (DEMO_MODE) return demoDashboard();
  const payload = await request<Partial<DashboardResponse> & Pick<DashboardResponse, "profile" | "activeJob" | "jobs">>(
    "/mobile/v1/dashboard",
    token,
  );
  return {
    profile: payload.profile,
    activeJob: payload.activeJob,
    jobs: payload.jobs ?? [],
    prioritySignals: Array.isArray(payload.prioritySignals) ? payload.prioritySignals : [],
    latestSignals: Array.isArray(payload.latestSignals) ? payload.latestSignals : [],
    trend: payload.trend && !Array.isArray(payload.trend) ? payload.trend : null,
  };
}

export function updateProfile(token: string, heightCm: number | null) {
  return request<MobileProfile>("/mobile/v1/me/profile", token, {
    method: "PATCH",
    body: JSON.stringify({ heightCm }),
  });
}

export function startKakaoLogin(token: string) {
  return request<{ authorizationUrl: string; expiresAt: string }>(
    "/mobile/v1/auth/kakao/start",
    token,
    { method: "POST" },
  );
}

export function exchangeKakaoCode(code: string) {
  return request<{
    accessToken: string;
    tokenType: "Bearer";
    sessionType: "account";
    expiresAt: string;
  }>("/mobile/v1/auth/kakao/exchange", null, {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function logout(token: string) {
  return request<{ status: string }>("/mobile/v1/auth/logout", token, {
    method: "POST",
  });
}

export function listJobs(token: string) {
  return request<{ jobs: ActiveAnalysisJob[]; nextCursor: string | null }>(
    "/mobile/v1/jobs",
    token,
  );
}

export function getJob(token: string, jobId: string) {
  if (DEMO_FIXTURES_ENABLED) {
    const fixture = demoJob(jobId);
    if (fixture) return Promise.resolve(fixture);
  }
  return request<ActiveAnalysisJob>(`/mobile/v1/jobs/${jobId}`, token);
}

export function getResult(token: string, jobId: string) {
  if (DEMO_FIXTURES_ENABLED) {
    const fixture = demoResult(jobId);
    if (fixture) return Promise.resolve(fixture);
  }
  return request<AnalysisResult>(`/mobile/v1/jobs/${jobId}/result`, token);
}

export function createResultVideoUrl(token: string, jobId: string) {
  return request<{ renderedVideoUrl: string }>(
    `/mobile/v1/jobs/${jobId}/result-video-url`,
    token,
    { method: "POST" },
  );
}

export async function uploadVideo(
  token: string,
  file: { uri: string; name: string; mimeType: string },
  heightCm: number,
  onProgress: (progress: number) => void,
): Promise<ActiveAnalysisJob> {
  const upload = await request<{
    object_name: string;
    upload_url: string;
    method: "PUT";
    required_headers: { "Content-Type": string };
  }>("/mobile/v1/uploads", token, {
    method: "POST",
    body: JSON.stringify({ filename: file.name, content_type: file.mimeType }),
  });

  const uploadTask = FileSystem.createUploadTask(
    upload.upload_url,
    file.uri,
    {
      httpMethod: upload.method,
      uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
      headers: upload.required_headers,
    },
    (progress) => {
      if (progress.totalBytesExpectedToSend > 0) {
        onProgress(
          progress.totalBytesSent / progress.totalBytesExpectedToSend,
        );
      }
    },
  );
  const uploadResult = await uploadTask.uploadAsync();
  if (!uploadResult || uploadResult.status < 200 || uploadResult.status >= 300) {
    throw new ApiError(
      "Video upload failed",
      uploadResult?.status ?? 0,
    );
  }

  await request("/mobile/v1/uploads/complete", token, {
    method: "POST",
    body: JSON.stringify({ object_name: upload.object_name }),
  });

  return request<ActiveAnalysisJob>("/mobile/v1/jobs", token, {
    method: "POST",
    body: JSON.stringify({
      inputObjectName: upload.object_name,
      userHeightCm: heightCm,
    }),
  });
}
