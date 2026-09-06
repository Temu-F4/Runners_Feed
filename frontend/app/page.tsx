"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";

import { getApiErrorMessage } from "../lib/api-error";

type Stage = "idle" | "upload" | "queue" | "analysis" | "result";
type JobStatus = "IDLE" | "QUEUED" | "PROCESSING" | "SUCCESS" | "FAILED" | "ERROR";

interface UploadResponse {
  object_name: string;
  upload_url: string;
  required_headers: { "Content-Type": string };
}

interface JobResponse {
  job_id: string;
  case_id: string;
  height_snapshot_m: number;
  status: JobStatus;
  created_at: string;
  completed_at: string | null;
  error?: string;
}

interface JobListResponse {
  jobs: JobResponse[];
}

interface ReportMetric {
  id: string;
  label: string;
  value: number | null;
  unit: string;
  description: string;
  measurement_basis: string;
  evidence_query: string[];
}

interface ReportEvidence {
  evidence_id: string;
  page: number;
  section: string;
  text: string;
  caveat: string;
  source: {
    title: string;
    authors: string;
    year: number;
    doi: string;
  };
}

interface NarrativeFinding {
  feature_id: string;
  label: string;
  measured_value: number | null;
  unit: string;
  interpretation: string;
  evidence_ids: string[];
  limitation: string;
}

type NarrativeReport =
  | {
      status: "success";
      model: string;
      overall_summary: string;
      findings: NarrativeFinding[];
      coaching_points: string[];
      disclaimer: string;
    }
  | {
      status: "disabled" | "unavailable";
      message: string;
      error_code?: string;
    };

interface AnalysisReport {
  video: {
    duration_seconds: number | null;
    fps: number | null;
    frame_count: number;
    width: number | null;
    height: number | null;
  };
  tracking: {
    tracked_frames: number;
    total_frames: number;
    coverage_pct: number | null;
    observed_keypoints_pct: number | null;
    average_keypoint_score_pct: number | null;
  };
  metrics: ReportMetric[];
  evidence: ReportEvidence[];
  narrative: NarrativeReport;
  notice: string;
}

interface SkeletonReplayData {
  schema_version: "skeleton-1.0";
  pose_model: "halpe26";
  coordinate_space: "normalized";
  fps: number;
  duration_ms: number;
  frames: Array<{
    t_ms: number;
    keypoints: Array<[number, number, number]>;
  }>;
}

const showInternalResults = process.env.NEXT_PUBLIC_SHOW_INTERNAL_RESULTS === "1";

const skeletonEdges = [
  [0, 1], [0, 2], [1, 3], [2, 4],
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
  [5, 11], [6, 12], [11, 12],
  [11, 13], [13, 15], [12, 14], [14, 16],
] as const;

function SkeletonReplay({ data }: { data: SkeletonReplayData }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.frames.length === 0) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const targetCanvas = canvas;
    const drawingContext = context;

    let animationFrame = 0;
    const startedAt = performance.now();
    const replayDuration = Math.max(
      data.duration_ms,
      data.frames[data.frames.length - 1].t_ms,
      1000,
    );

    function draw(now: number) {
      const elapsed = (now - startedAt) % replayDuration;
      let frame = data.frames[0];
      for (const candidate of data.frames) {
        if (candidate.t_ms > elapsed) break;
        frame = candidate;
      }

      drawingContext.fillStyle = "#07110f";
      drawingContext.fillRect(0, 0, targetCanvas.width, targetCanvas.height);
      drawingContext.strokeStyle = "#b9ff56";
      drawingContext.fillStyle = "#efffcf";
      drawingContext.lineWidth = 4;
      drawingContext.lineCap = "round";

      for (const [start, end] of skeletonEdges) {
        const first = frame.keypoints[start];
        const second = frame.keypoints[end];
        if (!first || !second || first[2] < 0.25 || second[2] < 0.25) continue;
        drawingContext.beginPath();
        drawingContext.moveTo(first[0] * targetCanvas.width, first[1] * targetCanvas.height);
        drawingContext.lineTo(second[0] * targetCanvas.width, second[1] * targetCanvas.height);
        drawingContext.stroke();
      }

      for (const [x, y, score] of frame.keypoints) {
        if (score < 0.25) continue;
        drawingContext.beginPath();
        drawingContext.arc(x * targetCanvas.width, y * targetCanvas.height, 5, 0, Math.PI * 2);
        drawingContext.fill();
      }
      animationFrame = requestAnimationFrame(draw);
    }

    animationFrame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animationFrame);
  }, [data]);

  return (
    <div className="skeleton-frame">
      <canvas ref={canvasRef} width="960" height="540" aria-label="러닝 자세 스켈레톤 재생" />
      <p>원본 영상 없이 관절 좌표만 재생합니다.</p>
    </div>
  );
}

const maxUploadBytes = 262144000;
const supportedVideoTypes: Record<string, string> = {
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
};
const stages: Exclude<Stage, "idle">[] = ["upload", "queue", "analysis", "result"];
const statusLabels: Record<JobStatus, string> = {
  IDLE: "대기",
  QUEUED: "대기 중",
  PROCESSING: "분석 중",
  SUCCESS: "완료",
  FAILED: "실패",
  ERROR: "오류",
};

function createCaseId(value: string) {
  const stem = value.replace(/\.(mp4|mov)$/i, "");
  const normalized = stem
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^[^A-Za-z0-9]+|[-]+$/g, "");
  return (normalized || `run-${Date.now()}`).slice(0, 64);
}

function formatJobDate(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(getApiErrorMessage(payload, response.status));
  return payload as T;
}

function getVideoContentType(filename: string): string | null {
  const normalized = filename.toLowerCase();
  const suffix = Object.keys(supportedVideoTypes).find((candidate) => normalized.endsWith(candidate));
  return suffix ? supportedVideoTypes[suffix] : null;
}

function uploadFile(url: string, file: File, contentType: string, onProgress: (ratio: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    request.setRequestHeader("Content-Type", contentType);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else reject(new Error(`영상 업로드에 실패했습니다. (${request.status})`));
    });
    request.addEventListener("error", () => reject(new Error("영상 업로드 연결에 실패했습니다.")));
    request.send(file);
  });
}

const wait = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [caseId, setCaseId] = useState("");
  const [userHeightCm, setUserHeightCm] = useState("");
  const [stage, setStage] = useState<Stage>("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("영상을 기다리고 있습니다");
  const [jobId, setJobId] = useState("—");
  const [jobStatus, setJobStatus] = useState<JobStatus>("IDLE");
  const [error, setError] = useState("");
  const [resultUrl, setResultUrl] = useState("");
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [skeleton, setSkeleton] = useState<SkeletonReplayData | null>(null);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<JobResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const resultRef = useRef<HTMLElement>(null);

  async function loadHistory() {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const response = await api<JobListResponse>("/jobs");
      setHistory(response.jobs);
    } catch {
      setHistoryError("분석 기록을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.");
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  function updateProgress(value: number, message: string, nextStage: Stage) {
    setProgress(value);
    setStatusText(message);
    setStage(nextStage);
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setError("");
    if (!selected) {
      setFile(null);
      return;
    }
    if (!getVideoContentType(selected.name)) {
      event.target.value = "";
      setFile(null);
      setError("MP4 또는 MOV 파일만 업로드할 수 있습니다. 다른 영상을 선택해 주세요.");
      return;
    }
    if (selected.size > maxUploadBytes) {
      event.target.value = "";
      setFile(null);
      setError("파일이 250 MiB를 초과했습니다. 더 짧거나 작은 영상을 선택해 주세요.");
      return;
    }
    setFile(selected);
    if (!caseId) setCaseId(createCaseId(selected.name));
  }

  async function pollJob(id: string) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < 60 * 60 * 1000) {
      const job = await api<JobResponse>(`/jobs/${id}`);
      setJobStatus(job.status);
      if (job.status === "SUCCESS") return;
      if (job.status === "FAILED") throw new Error(job.error || "분석 작업이 실패했습니다.");
      const processing = job.status === "PROCESSING";
      updateProgress(processing ? 68 : 48, processing ? "자세를 분석하고 있습니다" : "분석 순서를 기다리고 있습니다", processing ? "analysis" : "queue");
      await wait(2500);
    }
    throw new Error("분석 제한 시간을 초과했습니다.");
  }

  async function loadCompletedResult(id: string) {
    updateProgress(92, "분석 결과를 준비하고 있습니다", "result");
    if (!showInternalResults) {
      setJobStatus("SUCCESS");
      updateProgress(100, "분석이 완료됐습니다", "result");
      window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
      return;
    }
    try {
      const result = await api<{ rendered_video_url: string }>(`/jobs/${id}/result-url`, {
        method: "POST",
        body: "{}",
      });
      setResultUrl(result.rendered_video_url);
    } catch {
      setResultUrl("");
    }
    try {
      setReport(await api<AnalysisReport>(`/jobs/${id}/report`));
    } catch {
      setReport(null);
    }
    try {
      setSkeleton(await api<SkeletonReplayData>(`/jobs/${id}/skeleton`));
    } catch {
      setSkeleton(null);
    }
    setJobStatus("SUCCESS");
    updateProgress(100, "분석이 완료됐습니다", "result");
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  async function reopenJob(job: JobResponse) {
    setError("");
    setResultUrl("");
    setReport(null);
    setSkeleton(null);
    setJobId(job.job_id);
    setJobStatus(job.status);
    setRunning(true);

    try {
      if (job.status !== "SUCCESS") await pollJob(job.job_id);
      await loadCompletedResult(job.job_id);
      await loadHistory();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "분석 결과를 불러오지 못했습니다.");
      setStatusText("작업을 완료하지 못했습니다");
      setJobStatus("ERROR");
    } finally {
      setRunning(false);
    }
  }

  async function analyze() {
    setError("");
    setResultUrl("");
    setReport(null);
    setSkeleton(null);
    if (!file) return setError("먼저 MP4 또는 MOV 영상을 선택해 주세요.");
    const contentType = getVideoContentType(file.name);
    if (!contentType) return setError("MP4 또는 MOV 파일만 업로드할 수 있습니다.");
    if (file.size > maxUploadBytes) return setError("파일 크기는 250 MiB 이하여야 합니다.");
    const parsedHeightCm = Number(userHeightCm);
    if (!Number.isFinite(parsedHeightCm) || parsedHeightCm < 50 || parsedHeightCm > 250) {
      return setError("키는 50cm 이상 250cm 이하로 입력해 주세요.");
    }

    setRunning(true);
    try {
      updateProgress(5, "업로드 URL을 준비하고 있습니다", "upload");
      const upload = await api<UploadResponse>("/uploads", {
        method: "POST",
        body: JSON.stringify({ filename: file.name, content_type: contentType }),
      });
      await uploadFile(upload.upload_url, file, upload.required_headers["Content-Type"], (ratio) => {
        updateProgress(Math.max(8, Math.round(ratio * 32)), "영상을 안전하게 업로드하고 있습니다", "upload");
      });
      await api("/uploads/complete", { method: "POST", body: JSON.stringify({ object_name: upload.object_name }) });

      updateProgress(42, "분석 작업을 등록하고 있습니다", "queue");
      const job = await api<JobResponse>("/jobs", {
        method: "POST",
        body: JSON.stringify({
          case_id: createCaseId(caseId || file.name),
          input_object_name: upload.object_name,
          user_height_m: parsedHeightCm / 100,
        }),
      });
      setJobId(job.job_id);
      setJobStatus(job.status);
      await pollJob(job.job_id);

      await loadCompletedResult(job.job_id);
      await loadHistory();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "알 수 없는 오류가 발생했습니다.");
      setStatusText("작업을 완료하지 못했습니다");
      setJobStatus("ERROR");
    } finally {
      setRunning(false);
    }
  }

  const activeIndex = stages.indexOf(stage === "idle" ? "upload" : stage);
  const completedCount = history.filter((job) => job.status === "SUCCESS").length;
  const activeJob = history.find((job) => ["QUEUED", "PROCESSING"].includes(job.status));
  const latestJob = history[0];
  const fileSize = file ? `${(file.size / 1024 / 1024).toFixed(1)} MiB` : "최대 250 MiB";
  const parsedHeightCm = Number(userHeightCm);
  const canAnalyze = Boolean(
    file
    && getVideoContentType(file.name)
    && file.size <= maxUploadBytes
    && Number.isFinite(parsedHeightCm)
    && parsedHeightCm >= 50
    && parsedHeightCm <= 250
    && !running,
  );

  return (
    <main className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="Runners Feed 홈">
          <span className="brand-mark" aria-hidden="true">RF</span>
          <span><strong>RUNNERS FEED</strong><small>MOTION ANALYSIS</small></span>
        </a>
        <nav aria-label="주요 메뉴">
          <a href="#analyze">새 분석</a>
          <a href="#history">분석 기록</a>
          <span className="guest-chip">비회원 모드</span>
        </nav>
      </header>

      <section className="dashboard-hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">RUNNING FORM · VIDEO ANALYSIS</p>
          <h1>달리는 모습을<br /><span>측정 가능한 움직임으로.</span></h1>
          <p className="intro">측면 러닝 영상을 올리면 관절 움직임을 추적해 분석 결과를 만듭니다. 현재 결과는 내부 검증을 위한 실험적 측정이며 의료적 판단이 아닙니다.</p>
          <a className="hero-action" href="#analyze">새 영상 분석 <span aria-hidden="true">→</span></a>
        </div>

        <div className="dashboard-status" aria-label="분석 현황">
          <div className="status-head"><p>MY ANALYSIS</p><span>{historyLoading ? "동기화 중" : "현재 브라우저"}</span></div>
          <dl className="status-grid">
            <div><dt>전체 기록</dt><dd>{historyLoading ? "—" : history.length}</dd></div>
            <div><dt>완료</dt><dd>{historyLoading ? "—" : completedCount}</dd></div>
          </dl>
          <div className="latest-status">
            <span className="signal-dot" aria-hidden="true" />
            <div>
              <small>{activeJob ? "현재 분석" : "최근 분석"}</small>
              <strong>{activeJob?.case_id || latestJob?.case_id || "아직 분석 기록이 없습니다"}</strong>
            </div>
            <b>{activeJob ? statusLabels[activeJob.status] : latestJob ? statusLabels[latestJob.status] : "대기"}</b>
          </div>
        </div>
      </section>

      <section className="capture-guide" aria-label="촬영 안내">
        <div><span>01</span><strong>카메라는 측면에</strong><small>몸 전체와 진행 방향이 보이게 둡니다.</small></div>
        <div><span>02</span><strong>전신이 프레임 안에</strong><small>머리부터 발끝까지 잘리지 않게 촬영합니다.</small></div>
        <div><span>03</span><strong>흔들림 없이 3–10초</strong><small>한 사람이 일정한 속도로 달리는 구간을 사용합니다.</small></div>
      </section>

      <section className="analysis-workspace" id="analyze" aria-labelledby="upload-title">
        <div className="section-heading wide-heading">
          <div><p className="step-label">NEW ANALYSIS</p><h2 id="upload-title">새 러닝 분석</h2></div>
          <p>MP4 또는 MOV · 최대 250 MiB<br />원본 영상은 분석 후 정리 대상입니다.</p>
        </div>

        <div className="analysis-grid">
          <div className="upload-card">
            <label className={`drop-zone ${file ? "selected" : ""}`} htmlFor="video-file">
              <input id="video-file" type="file" accept="video/mp4,video/quicktime,.mp4,.mov" onChange={selectFile} />
              <span className="drop-code" aria-hidden="true">VIDEO / 01</span>
              <strong>{file?.name || "분석할 영상을 선택하세요"}</strong>
              <span>{file ? `${fileSize} · 선택 완료` : "눌러서 파일 선택"}</span>
              <b>{file ? "다른 영상 선택" : "영상 선택"}</b>
            </label>

            <div className="form-row">
              <label className="field" htmlFor="case-id">
                <span>분석 이름</span>
                <input id="case-id" value={caseId} onChange={(event) => setCaseId(event.target.value)} maxLength={64} placeholder="morning-run" autoComplete="off" />
                <small>기록에서 영상을 구분할 이름입니다.</small>
              </label>
              <label className="field" htmlFor="user-height-cm">
                <span>분석 대상 키</span>
                <div className="unit-field">
                  <input id="user-height-cm" type="number" min="50" max="250" step="0.1" inputMode="decimal" value={userHeightCm} onChange={(event) => setUserHeightCm(event.target.value)} placeholder="175" autoComplete="off" />
                  <b>cm</b>
                </div>
                <small>이 분석에만 적용되며 50–250cm를 지원합니다.</small>
              </label>
            </div>

            <button className="primary-button" type="button" onClick={analyze} disabled={!canAnalyze}>
              <span>{running ? "분석을 진행하고 있습니다" : "확인하고 분석 시작"}</span><span aria-hidden="true">→</span>
            </button>
            <p className="privacy-note">업로드된 원본은 공개되지 않으며 모델 학습에 사용하지 않습니다.</p>
            <p className="error-message" role="alert">{error}</p>
          </div>

          <aside className="process-card" aria-labelledby="process-title">
            <div className="process-head">
              <div><p className="step-label">LIVE STATUS</p><h3 id="process-title">분석 진행</h3></div>
              <strong>{progress}<span>%</span></strong>
            </div>
            <progress max="100" value={progress}>{progress}%</progress>
            <p className="status-copy" aria-live="polite">{statusText}</p>
            <ol className="timeline">
              {[["영상 업로드", "Object Storage"], ["작업 등록", "Queue"], ["관절 위치 분석", "RTMPose"], ["결과 생성", "Report & replay"]].map(([title, detail], index) => (
                <li key={title} className={stage !== "idle" && index < activeIndex ? "done" : stage !== "idle" && index === activeIndex ? "active" : ""}>
                  <span>{String(index + 1).padStart(2, "0")}</span><div><strong>{title}</strong><small>{detail}</small></div>
                </li>
              ))}
            </ol>
            <dl className="job-meta">
              <div><dt>Job ID</dt><dd>{jobId}</dd></div>
              <div><dt>Status</dt><dd className={`status-${jobStatus.toLowerCase()}`}>{statusLabels[jobStatus]}</dd></div>
            </dl>
          </aside>
        </div>
      </section>

      <section className="history-section" id="history" aria-labelledby="history-title">
        <div className="section-heading">
          <div><p className="step-label">ANALYSIS HISTORY</p><h2 id="history-title">이 브라우저의 분석 기록</h2></div>
          <button className="text-button" type="button" onClick={() => void loadHistory()} disabled={historyLoading}>{historyLoading ? "불러오는 중" : "새로고침"}</button>
        </div>
        {historyError && <p className="history-message" role="alert">{historyError}</p>}
        {!historyLoading && !historyError && history.length === 0 && <p className="history-message">아직 저장된 분석 기록이 없습니다. 첫 영상을 선택해 시작해 보세요.</p>}
        {history.length > 0 && (
          <ol className="history-list">
            {history.map((job, index) => {
              const canOpen = ["QUEUED", "PROCESSING", "SUCCESS"].includes(job.status);
              return (
                <li key={job.job_id}>
                  <span className="history-index">{String(index + 1).padStart(2, "0")}</span>
                  <div className="history-primary"><strong>{job.case_id}</strong><span>{formatJobDate(job.created_at)}</span></div>
                  <div className="history-detail"><span>{Math.round(job.height_snapshot_m * 100)}cm</span><span className={`history-status status-${job.status.toLowerCase()}`}>{statusLabels[job.status]}</span></div>
                  <button type="button" onClick={() => void reopenJob(job)} disabled={running || !canOpen}>{job.status === "SUCCESS" ? "결과 보기" : canOpen ? "이어 보기" : "열 수 없음"}<span aria-hidden="true">→</span></button>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      {jobStatus === "SUCCESS" && !showInternalResults && (
        <section ref={resultRef} className="completion-section" aria-labelledby="completion-title">
          <p className="step-label">ANALYSIS COMPLETE</p>
          <h2 id="completion-title">영상 분석이 완료됐습니다.</h2>
          <p>측정값과 코칭 결과는 정확도 검증을 마친 뒤 제공할 예정입니다. 현재 베타에서는 완료 여부만 확인할 수 있습니다.</p>
          <a href="#analyze">다른 영상 분석 <span aria-hidden="true">→</span></a>
        </section>
      )}

      {showInternalResults && (resultUrl || skeleton) && (
        <section ref={resultRef} className="result-section" aria-labelledby="result-title">
          <div className="result-copy"><p className="step-label">ANALYSIS OUTPUT</p><h2 id="result-title">움직임 재생</h2><p>{resultUrl ? "관절 포인트가 합성된 테스트 영상을 확인할 수 있습니다." : "결과 영상의 보관기간이 지나 관절 좌표만 재생합니다."}</p><span>내부 검증용 · 정확도 검토 전</span></div>
          {resultUrl ? <div className="video-frame"><video src={resultUrl} controls playsInline preload="metadata" /></div> : skeleton ? <SkeletonReplay data={skeleton} /> : null}
        </section>
      )}

      {showInternalResults && report && (
        <section className="report-section" aria-labelledby="report-title">
          <div className="report-heading"><div><p className="step-label">MEASUREMENT REPORT</p><h2 id="report-title">러닝 자세 측정 리포트</h2></div><p>{report.notice}</p></div>
          <div className="verification-banner"><strong>검증 중인 결과입니다.</strong><span>현재 측정값과 코칭 문구는 내부 테스트용이며 정확도 검토 전 외부 사용자 판단에 사용하지 않습니다.</span></div>
          <dl className="report-summary">
            <div><dt>분석 프레임</dt><dd>{report.tracking.tracked_frames} / {report.tracking.total_frames}</dd></div>
            <div><dt>러너 추적률</dt><dd>{report.tracking.coverage_pct ?? "—"}%</dd></div>
            <div><dt>관절 관측률</dt><dd>{report.tracking.observed_keypoints_pct ?? "—"}%</dd></div>
            <div><dt>평균 신뢰도</dt><dd>{report.tracking.average_keypoint_score_pct ?? "—"}%</dd></div>
          </dl>
          <div className="metrics-grid">
            {report.metrics.map((metric, index) => <article className="metric-card" key={metric.id}><div><span>{String(index + 1).padStart(2, "0")}</span><p>{metric.label}</p></div><strong>{metric.value ?? "—"}<span>{metric.value === null ? "" : metric.unit}</span></strong><small>{metric.description}</small><p>{metric.measurement_basis}</p></article>)}
          </div>
          {report.narrative.status === "success" ? (
            <div className="narrative-block">
              <div className="narrative-intro"><p className="step-label">AI INTERPRETATION · {report.narrative.model}</p><h3>{report.narrative.overall_summary}</h3></div>
              {report.narrative.findings.length > 0 && <div className="findings-list">{report.narrative.findings.map((finding) => <article className="finding-card" key={finding.feature_id}><div><p>{finding.label}</p><strong>{finding.measured_value ?? "—"}<span>{finding.measured_value === null ? "" : finding.unit}</span></strong></div><div><p>{finding.interpretation}</p><small>{finding.limitation}</small>{finding.evidence_ids.length > 0 && <small>근거: {finding.evidence_ids.join(", ")}</small>}</div></article>)}</div>}
              <div className="coaching-block">{report.narrative.coaching_points.length > 0 && <><h3>테스트 결과에서 확인할 항목</h3><ol>{report.narrative.coaching_points.map((point) => <li key={point}>{point}</li>)}</ol></>}<p>{report.narrative.disclaimer}</p></div>
            </div>
          ) : <p className="narrative-unavailable">{report.narrative.message}</p>}
          <div className="evidence-block"><p className="step-label">EVIDENCE</p><h3>리포트에 연결된 근거</h3><div className="evidence-list">{report.evidence.map((item) => <article key={item.evidence_id}><p>p.{item.page} · {item.section}</p><strong>{item.text}</strong><small>{item.caveat}</small></article>)}</div>{report.evidence[0] && <a href={`https://doi.org/${report.evidence[0].source.doi}`} target="_blank" rel="noreferrer">{report.evidence[0].source.authors} ({report.evidence[0].source.year}) · DOI {report.evidence[0].source.doi}</a>}</div>
        </section>
      )}

      <nav className="mobile-nav" aria-label="모바일 주요 메뉴">
        <a href="#top"><span>01</span>홈</a>
        <a href="#analyze"><span>02</span>새 분석</a>
        <a href="#history"><span>03</span>기록</a>
      </nav>
      <footer><span>RUNNERS FEED</span><p>러닝 자세 영상 분석 · 내부 베타</p><a href="#top">위로 이동 ↑</a></footer>
    </main>
  );
}
