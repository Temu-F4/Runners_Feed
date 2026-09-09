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
  score?: number | null;
  scoreMethod?: string | null;
  denominatorPolicy?: "all_frames" | "evaluated_frames" | string;
  goodFrameCount?: number;
  evaluatedFrameCount?: number;
  sourceFrameCount?: number;
  evaluationCoveragePct?: number | null;
  confidenceAssumed?: boolean;
  visualization?: {
    kind: "range_bar" | "line" | string;
    x_axis: "aggregate_ratio" | "measurable_frame" | "video_frame" | string;
    placement: "summary_metrics" | "feature_grid" | string;
  } | null;
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
  confidenceAssumed?: boolean;
  score?: number | null;
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
  postureScore?: number | null;
  runMetrics?: {
    pacePerKm: string | null;
    cadenceSpm: number | null;
    strideLengthM: number | null;
    estimationBasis: string | null;
  } | null;
  media?: {
    renderedVideoUrl: string | null;
    renderedVideoExpiresAt: string | null;
    skeletonVideoUrl: string | null;
  } | null;
  runtimeMetadata?: {
    promptVersion: string | null;
    model: string | null;
    validatorVersion: string | null;
    inputTokens: number | null;
    outputTokens: number | null;
  } | null;
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
  postureScore?: number | null;
  skeletonVideoUrl?: string | null;
  renderedVideoExpiresAt?: string | null;
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
