export type JobStatus =
  | "IDLE"
  | "QUEUED"
  | "PROCESSING"
  | "SUCCESS"
  | "FAILED"
  | "ERROR";

export type JobStage =
  | "upload"
  | "queue"
  | "keypoints"
  | "features"
  | "validation"
  | "result";

export type ConfidenceLevel = "high" | "medium" | "low" | "excluded";
export type FeatureVerdict = "improve" | "maintain" | "review" | "excluded";

export interface ReferenceRange {
  kind: "recommended" | "reference";
  min: number;
  max: number;
  unit: string;
  criterionVersion: string;
  evidenceIds: string[];
}

export interface FrameMeasurement {
  frameIndex: number;
  timestampMs: number;
  value: number | null;
  confidencePct: number | null;
}

export interface FeatureAnalysis {
  featureId: string;
  label: string;
  priority: number | null;
  verdict: FeatureVerdict;
  representativeValue: number | null;
  unit: string;
  aggregation: string;
  referenceRange: ReferenceRange | null;
  series: FrameMeasurement[];
  interpretation: string;
  coachingAction: string | null;
  confidencePct: number | null;
  confidenceLevel: ConfidenceLevel;
  limitation: string;
  evidenceIds: string[];
}

export interface ValidatedNarrative {
  status: "success" | "unavailable";
  model: string | null;
  priorityActions: Array<Record<string, unknown>>;
  maintainActions: Array<Record<string, unknown>>;
  disclaimer: string;
  validatorVersion: string;
}

export interface AnalysisResult {
  jobId: string;
  createdAt: string;
  completedAt: string;
  analyzedFrameCount: number;
  totalFrameCount: number;
  features: FeatureAnalysis[];
  evidence: EvidenceItem[];
  narrative: ValidatedNarrative;
}

export interface EvidenceItem {
  evidenceId: string;
  frameIndex: number | null;
  timestampMs: number | null;
  type: string;
  label: string;
  description: string;
  uri: string | null;
  metadata: Record<string, unknown>;
}

export interface ActiveAnalysisJob {
  jobId: string;
  title: string;
  caseId: string;
  status: JobStatus;
  stage: JobStage;
  progressPct: number | null;
  estimatedCompletionSeconds: number | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  updatedAt: string;
  heightCm: number | null;
  error: string | null;
}

export interface MobileProfile {
  userId: string;
  sessionType: "guest" | "account";
  authenticated: boolean;
  provider: string | null;
  email: string | null;
  displayName: string | null;
  heightCm: number | null;
  kakaoLoginEnabled: boolean;
}

export interface DashboardResponse {
  profile: MobileProfile;
  activeJob: ActiveAnalysisJob | null;
  jobs: ActiveAnalysisJob[];
  prioritySignals: Array<Record<string, unknown>>;
  trend: Array<Record<string, unknown>>;
}
