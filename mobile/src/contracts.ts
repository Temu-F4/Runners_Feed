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

export interface PostureSignal {
  featureId: string;
  label: string;
  priority: number | null;
  verdict: FeatureVerdict;
  value: number | null;
  unit: string;
  referenceRange: ReferenceRange | null;
  message: string;
  confidencePct: number | null;
  confidenceLevel: ConfidenceLevel;
}

export interface TrendPoint {
  recordedAt: string;
  value: number | null;
}

export interface TrendSummary {
  featureId: string;
  label: string;
  unit: string;
  points: TrendPoint[];
  deltaPct: number | null;
  summary: string | null;
}

export interface EvidenceSource {
  evidenceId: string;
  title: string;
  authors: string;
  year: number | null;
  doi: string | null;
  url: string | null;
  page: number | null;
  section: string | null;
  criterionVersion: string | null;
  excerptSummary: string;
  caveat: string;
}

export interface CoachingAction {
  featureId: string;
  kind: "improve" | "maintain";
  text: string;
  measurementReference: {
    value: number | null;
    unit: string;
    referenceMin: number | null;
    referenceMax: number | null;
  } | null;
}

export interface ValidatedNarrative {
  status: "success" | "unavailable";
  model: string | null;
  summary: string | null;
  priorityActions: CoachingAction[];
  maintainActions: CoachingAction[];
  disclaimer: string;
  validatorVersion: string;
}

export interface AnalysisResult {
  jobId: string;
  modelId: string | null;
  modelRelease: string | null;
  createdAt: string;
  completedAt: string;
  analyzedFrameCount: number;
  totalFrameCount: number;
  features: FeatureAnalysis[];
  evidence: EvidenceItem[];
  narrative: ValidatedNarrative;
}

export interface EvidenceItem extends EvidenceSource {
  evidenceId: string;
  frameIndex: number | null;
  timestampMs: number | null;
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
  modelId: string | null;
  modelRelease: string | null;
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
  prioritySignals: PostureSignal[];
  latestSignals: PostureSignal[];
  trend: TrendSummary | null;
}
