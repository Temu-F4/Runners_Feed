"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";

type Stage = "idle" | "upload" | "queue" | "analysis" | "result";
type JobStatus = "IDLE" | "QUEUED" | "PROCESSING" | "SUCCESS" | "FAILED" | "ERROR";

interface UploadResponse {
  object_name: string;
  upload_url: string;
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
  const stem = value.replace(/\.mp4$/i, "");
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
  if (!response.ok) throw new Error(payload.detail || `요청에 실패했습니다. (${response.status})`);
  return payload as T;
}

function uploadFile(url: string, file: File, onProgress: (ratio: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    request.setRequestHeader("Content-Type", "video/mp4");
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
    } catch (caught) {
      setHistoryError(caught instanceof Error ? caught.message : "분석 기록을 불러오지 못했습니다.");
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
    setFile(selected);
    if (selected && !caseId) setCaseId(createCaseId(selected.name));
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
    if (!file) return setError("먼저 MP4 영상을 선택해 주세요.");
    if (!file.name.toLowerCase().endsWith(".mp4")) return setError("MP4 파일만 업로드할 수 있습니다.");
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
        body: JSON.stringify({ filename: file.name, content_type: "video/mp4" }),
      });
      await uploadFile(upload.upload_url, file, (ratio) => {
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

  return (
    <main className="shell">
      <header className="hero">
        <p className="eyebrow">RUNNERS FEED · MOTION LAB</p>
        <h1>달리는 순간을<br /><span>데이터로 읽습니다.</span></h1>
        <p className="intro">MP4 영상을 올리면 자세 추정 파이프라인이 프레임을 분석하고, 관절 포인트가 표시된 결과 영상을 만듭니다.</p>
      </header>

      <section className="workspace" aria-labelledby="upload-title">
        <div className="panel upload-panel">
          <div className="panel-heading"><p className="step-label">01 · INPUT</p><h2 id="upload-title">분석할 영상</h2></div>
          <label className="drop-zone" htmlFor="video-file">
            <input id="video-file" type="file" accept="video/mp4,.mp4" onChange={selectFile} />
            <span className="drop-icon" aria-hidden="true">↗</span>
            <strong>{file?.name || "MP4 파일을 선택하세요"}</strong>
            <span>최대 250 MiB · 원본은 비공개 저장</span>
          </label>
          <label className="field" htmlFor="case-id">
            <span>분석 이름</span>
            <input id="case-id" value={caseId} onChange={(event) => setCaseId(event.target.value)} maxLength={64} placeholder="morning-run" autoComplete="off" />
          </label>
          <label className="field" htmlFor="user-height-cm">
            <span>키 (cm)</span>
            <input
              id="user-height-cm"
              type="number"
              min="50"
              max="250"
              step="0.1"
              inputMode="decimal"
              value={userHeightCm}
              onChange={(event) => setUserHeightCm(event.target.value)}
              placeholder="175"
              autoComplete="off"
            />
          </label>
          <button className="primary-button" type="button" onClick={analyze} disabled={running}>분석 시작 <span aria-hidden="true">→</span></button>
          <p className="error-message" role="alert">{error}</p>
        </div>

        <div className="panel process-panel">
          <div className="panel-heading"><p className="step-label">02 · PROCESS</p><h2>분석 진행</h2></div>
          <ol className="timeline">
            {[["영상 업로드", "Object Storage"], ["작업 등록", "Celery Queue"], ["자세 분석", "RTMPose Halpe26"], ["결과 생성", "Rendered MP4"]].map(([title, detail], index) => (
              <li key={title} className={stage !== "idle" && index < activeIndex ? "done" : stage !== "idle" && index === activeIndex ? "active" : ""}>
                <span>{index + 1}</span><div><strong>{title}</strong><small>{detail}</small></div>
              </li>
            ))}
          </ol>
          <div className="progress-block">
            <div className="progress-copy"><span aria-live="polite">{statusText}</span><span>{progress}%</span></div>
            <progress max="100" value={progress}>{progress}%</progress>
          </div>
          <dl className="job-meta">
            <div><dt>Job ID</dt><dd>{jobId}</dd></div>
            <div><dt>Status</dt><dd>{jobStatus}</dd></div>
          </dl>
        </div>
      </section>

      <section className="history-section" aria-labelledby="history-title">
        <div className="history-heading">
          <div>
            <p className="step-label">HISTORY</p>
            <h2 id="history-title">이 브라우저의 분석 기록</h2>
          </div>
          <button type="button" onClick={() => void loadHistory()} disabled={historyLoading}>
            {historyLoading ? "불러오는 중" : "새로고침"}
          </button>
        </div>

        {historyError && <p className="history-message" role="alert">{historyError}</p>}
        {!historyLoading && !historyError && history.length === 0 && (
          <p className="history-message">아직 저장된 분석 기록이 없습니다.</p>
        )}

        {history.length > 0 && (
          <ol className="history-list">
            {history.map((job) => {
              const canOpen = ["QUEUED", "PROCESSING", "SUCCESS"].includes(job.status);
              return (
                <li key={job.job_id}>
                  <div className="history-primary">
                    <strong>{job.case_id}</strong>
                    <span>{formatJobDate(job.created_at)}</span>
                  </div>
                  <div className="history-detail">
                    <span>{Math.round(job.height_snapshot_m * 100)}cm</span>
                    <span className={`history-status status-${job.status.toLowerCase()}`}>
                      {statusLabels[job.status]}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => void reopenJob(job)}
                    disabled={running || !canOpen}
                  >
                    {job.status === "SUCCESS" ? "결과 보기" : canOpen ? "이어 보기" : "열 수 없음"}
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      {(resultUrl || skeleton) && (
        <section ref={resultRef} className="result-section" aria-labelledby="result-title">
          <div className="result-copy"><p className="step-label">03 · RESULT</p><h2 id="result-title">분석이 완료됐습니다.</h2><p>{resultUrl ? "관절 포인트가 합성된 영상을 확인하세요." : "결과 영상의 보관기간이 지나 관절 움직임만 표시합니다."}</p></div>
          {resultUrl ? (
            <div className="video-frame"><video src={resultUrl} controls playsInline preload="metadata" /></div>
          ) : skeleton ? (
            <SkeletonReplay data={skeleton} />
          ) : null}
        </section>
      )}

      {report && (
        <section className="report-section" aria-labelledby="report-title">
          <div className="report-heading">
            <div>
              <p className="step-label">04 · REPORT</p>
              <h2 id="report-title">러닝 자세 측정 리포트</h2>
            </div>
            <p>{report.notice}</p>
          </div>

          <dl className="report-summary">
            <div><dt>분석 프레임</dt><dd>{report.tracking.tracked_frames} / {report.tracking.total_frames}</dd></div>
            <div><dt>러너 추적률</dt><dd>{report.tracking.coverage_pct ?? "—"}%</dd></div>
            <div><dt>관절 관측률</dt><dd>{report.tracking.observed_keypoints_pct ?? "—"}%</dd></div>
            <div><dt>평균 신뢰도</dt><dd>{report.tracking.average_keypoint_score_pct ?? "—"}%</dd></div>
          </dl>

          <div className="metrics-grid">
            {report.metrics.map((metric) => (
              <article className="metric-card" key={metric.id}>
                <p>{metric.label}</p>
                <strong>{metric.value ?? "—"}<span>{metric.value === null ? "" : metric.unit}</span></strong>
                <small>{metric.description}</small>
              </article>
            ))}
          </div>

          {report.narrative.status === "success" ? (
            <div className="narrative-block">
              <div className="narrative-intro">
                <p className="step-label">AI INTERPRETATION · {report.narrative.model}</p>
                <h3>{report.narrative.overall_summary}</h3>
              </div>

              {report.narrative.findings.length > 0 && (
                <div className="findings-list">
                  {report.narrative.findings.map((finding) => (
                  <article className="finding-card" key={finding.feature_id}>
                    <div>
                      <p>{finding.label}</p>
                      <strong>{finding.measured_value ?? "—"}<span>{finding.measured_value === null ? "" : finding.unit}</span></strong>
                    </div>
                    <div>
                      <p>{finding.interpretation}</p>
                      <small>{finding.limitation}</small>
                      {finding.evidence_ids.length > 0 && (
                        <small>근거: {finding.evidence_ids.join(", ")}</small>
                      )}
                    </div>
                  </article>
                  ))}
                </div>
              )}

              <div className="coaching-block">
                {report.narrative.coaching_points.length > 0 && (
                  <>
                    <h3>이번 영상에서 시도해 볼 점</h3>
                    <ol>
                      {report.narrative.coaching_points.map((point) => <li key={point}>{point}</li>)}
                    </ol>
                  </>
                )}
                <p>{report.narrative.disclaimer}</p>
              </div>
            </div>
          ) : (
            <p className="narrative-unavailable">{report.narrative.message}</p>
          )}

          <div className="evidence-block">
            <p className="step-label">EVIDENCE</p>
            <h3>리포트에 사용된 논문 근거</h3>
            <div className="evidence-list">
              {report.evidence.map((item) => (
                <article key={item.evidence_id}>
                  <p>p.{item.page} · {item.section}</p>
                  <strong>{item.text}</strong>
                  <small>{item.caveat}</small>
                </article>
              ))}
            </div>
            {report.evidence[0] && (
              <a href={`https://doi.org/${report.evidence[0].source.doi}`} target="_blank" rel="noreferrer">
                {report.evidence[0].source.authors} ({report.evidence[0].source.year}) · DOI {report.evidence[0].source.doi}
              </a>
            )}
          </div>
        </section>
      )}
    </main>
  );
}
