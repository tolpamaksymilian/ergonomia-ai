export type AnalysisProcessingStage =
  | "queued"
  | "ready-for-ai"
  | "pose-claimed"
  | "ready-for-ergonomics"
  | "ergonomics-processing"
  | "ergonomics-failed"
  | "ready-for-risk-assessment"
  | "risk-processing"
  | "risk-failed"
  | "ready-for-report";

export type ErgonomicsMetricStatistics = {
  valid_frames: number;
  invalid_frames: number;
  valid_ratio: number;
  mean: number | null;
  median: number | null;
  minimum: number | null;
  maximum: number | null;
  percentile_95: number | null;
};

export type ErgonomicsMetricsSummary = {
  metric_names: string[];
  metrics: Record<string, ErgonomicsMetricStatistics>;
  frame_count: number;
  metric_count: number;
  valid_metric_values: number;
  possible_metric_values: number;
  valid_metric_ratio: number;
};

export type ErgonomicsAnalysisMetadata = {
  ergonomics_metrics_path: string | null;
  ergonomics_metrics_version: string | null;
  ergonomics_processed_frames: number | null;
  ergonomics_valid_metric_ratio: number | string | null;
  ergonomics_metrics_summary: ErgonomicsMetricsSummary | null;
  ergonomics_completed_at: string | null;
  ergonomics_error_code: string | null;
  ergonomics_error_message: string | null;
};

export type RiskLevel =
  | "low"
  | "moderate"
  | "high"
  | "critical"
  | "insufficient_data";

export type RiskProfileStatus =
  | "development"
  | "draft"
  | "approved"
  | "archived";

export type RiskDominantMetricSummary = {
  metric_name: string;
  level: Exclude<RiskLevel, "insufficient_data">;
  weighted_score: number | null;
};

export type RiskAssessmentSummary = {
  risk_engine_version: string;
  profile: {
    profile_id: string;
    profile_name: string;
    profile_version: string;
    status: RiskProfileStatus;
    normative_method: string | null;
  };
  overall_level: RiskLevel;
  overall_score: number | null;
  data_coverage: number;
  valid_metric_ratio: number;
  frame_count: number;
  enabled_metric_count: number;
  evaluated_zones: string[];
  insufficient_zones: string[];
  highest_risk_zones: string[];
  decision_reasons: string[];
  dominant_metrics: RiskDominantMetricSummary[];
  key_frames_count: number;
  key_frame_timestamps_seconds: number[];
  insufficient_data: boolean;
};

export type RiskAnalysisMetadata = {
  risk_assessment_path: string | null;
  risk_assessment_version: string | null;
  risk_profile_id: string | null;
  risk_profile_version: string | null;
  risk_profile_status: RiskProfileStatus | null;
  risk_processed_frames: number | null;
  risk_valid_metric_ratio: number | string | null;
  risk_overall_level: RiskLevel | null;
  risk_assessment_summary: RiskAssessmentSummary | null;
  risk_completed_at: string | null;
  risk_error_code: string | null;
  risk_error_message: string | null;
  risk_worker_id: string | null;
  risk_started_at: string | null;
  risk_attempts: number;
};
