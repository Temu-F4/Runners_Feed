const fileInput = document.querySelector("#video-file");
const fileLabel = document.querySelector("#file-label");
const caseInput = document.querySelector("#case-id");
const analyzeButton = document.querySelector("#analyze-button");
const errorMessage = document.querySelector("#form-error");
const statusText = document.querySelector("#status-text");
const progress = document.querySelector("#progress");
const progressValue = document.querySelector("#progress-value");
const jobIdElement = document.querySelector("#job-id");
const jobStatusElement = document.querySelector("#job-status");
const resultSection = document.querySelector("#result-section");
const resultVideo = document.querySelector("#result-video");

const maxUploadBytes = 262144000;

function setProgress(value, message, stage) {
  progress.value = value;
  progress.textContent = `${value}%`;
  progressValue.textContent = `${value}%`;
  statusText.textContent = message;

  const order = ["upload", "queue", "analysis", "result"];
  const activeIndex = order.indexOf(stage);
  document.querySelectorAll("#timeline li").forEach((item, index) => {
    item.classList.toggle("done", activeIndex >= 0 && index < activeIndex);
    item.classList.toggle("active", index === activeIndex);
  });
}

function createCaseId(filename) {
  const stem = filename.replace(/\.mp4$/i, "");
  const normalized = stem
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^[^A-Za-z0-9]+|[-]+$/g, "");
  return (normalized || `run-${Date.now()}`).slice(0, 64);
}

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `요청에 실패했습니다. (${response.status})`);
  }
  return payload;
}

function uploadFile(url, file, onProgress) {
  return new Promise((resolve, reject) => {
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

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function pollJob(jobId) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 60 * 60 * 1000) {
    const job = await api(`/jobs/${jobId}`);
    jobStatusElement.textContent = job.status;
    if (job.status === "SUCCESS") return job;
    if (job.status === "FAILED") throw new Error(job.error || "분석 작업이 실패했습니다.");
    setProgress(job.status === "PROCESSING" ? 68 : 48, job.status === "PROCESSING" ? "자세를 분석하고 있습니다" : "분석 순서를 기다리고 있습니다", job.status === "PROCESSING" ? "analysis" : "queue");
    await wait(2500);
  }
  throw new Error("분석 제한 시간을 초과했습니다.");
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;
  fileLabel.textContent = file.name;
  if (!caseInput.value) caseInput.value = createCaseId(file.name);
});

analyzeButton.addEventListener("click", async () => {
  const file = fileInput.files[0];
  errorMessage.textContent = "";
  resultSection.hidden = true;
  resultVideo.removeAttribute("src");

  if (!file) {
    errorMessage.textContent = "먼저 MP4 영상을 선택해 주세요.";
    return;
  }
  if (!file.name.toLowerCase().endsWith(".mp4")) {
    errorMessage.textContent = "MP4 파일만 업로드할 수 있습니다.";
    return;
  }
  if (file.size > maxUploadBytes) {
    errorMessage.textContent = "파일 크기는 250 MiB 이하여야 합니다.";
    return;
  }

  analyzeButton.disabled = true;
  try {
    setProgress(5, "업로드 URL을 준비하고 있습니다", "upload");
    const upload = await api("/uploads", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, content_type: "video/mp4" }),
    });

    await uploadFile(upload.upload_url, file, (ratio) => {
      setProgress(Math.max(8, Math.round(ratio * 32)), "영상을 안전하게 업로드하고 있습니다", "upload");
    });

    await api("/uploads/complete", {
      method: "POST",
      body: JSON.stringify({ object_name: upload.object_name }),
    });

    setProgress(42, "분석 작업을 등록하고 있습니다", "queue");
    const job = await api("/jobs", {
      method: "POST",
      body: JSON.stringify({
        case_id: createCaseId(caseInput.value || file.name),
        input_object_name: upload.object_name,
      }),
    });
    jobIdElement.textContent = job.job_id;
    jobStatusElement.textContent = job.status;

    await pollJob(job.job_id);
    setProgress(92, "결과 영상을 준비하고 있습니다", "result");
    const result = await api(`/jobs/${job.job_id}/result-url`, { method: "POST", body: "{}" });
    resultVideo.src = result.rendered_video_url;
    resultSection.hidden = false;
    setProgress(100, "분석이 완료됐습니다", "result");
    jobStatusElement.textContent = "SUCCESS";
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    errorMessage.textContent = error.message;
    statusText.textContent = "작업을 완료하지 못했습니다";
    jobStatusElement.textContent = "ERROR";
  } finally {
    analyzeButton.disabled = false;
  }
});
