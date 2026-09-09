import type { JobStage, JobStatus } from "./contracts";

export const progressPhaseIndex: Record<JobStage, number> = {
  upload: 0,
  queue: 1,
  keypoints: 2,
  features: 3,
  validation: 3,
  result: 4,
};

export function pollingIsFinal(status: JobStatus) {
  return status === "SUCCESS" || status === "FAILED" || status === "ERROR";
}
