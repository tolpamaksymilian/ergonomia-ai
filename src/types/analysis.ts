export type AnalysisProcessingStage =
  | "queued"
  | "claimed"
  | "claimed-for-preprocessing"
  | "downloading-source"
  | "preprocessing-video"
  | "saving-preprocessing-results"
  | "ready-for-ai"
  | "pose-claimed"
  | "downloading-for-pose"
  | "downloading-for-pose-v3"
  | "initializing-pose-inference"
  | "pose-inference"
  | "pose-inference-active-segment-v3"
  | "pose-v3-rendering-validated-results"
  | "uploading-pose-results"
  | "uploading-pose-results-v3"
  | "saving-pose-results"
  | "saving-pose-results-v3"
  | "ready-for-ergonomics"
  | "ergonomics-processing"
  | "ergonomics-failed"
  | "ready-for-risk-assessment"
  | "risk-processing"
  | "risk-failed"
  | "ready-for-report"
  | "report-processing"
  | "report-failed"
  | "processing-failed"
  | "completed";

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

export type ReportRiskProfile = {
  profile_id: string;
  profile_name: string;
  profile_version: string;
  profile_status: RiskProfileStatus;
  normative_method: string | null;
};

export type ReportRiskSummary = {
  overall_level: RiskLevel;
  overall_status: "classified" | "insufficient_data";
  insufficient_data: boolean;
  profile: ReportRiskProfile;
  dominant_zones: string[];
  dominant_metrics: string[];
  key_frames_count: number;
  valid_metric_ratio: number;
};

export type ReportBodyArea = {
  area_id: string;
  label: string;
  level: RiskLevel;
  insufficient_data: boolean;
  coverage?: number;
  active_metrics?: number;
  metrics_with_sufficient_data?: number;
};

export type ReportMetricSummary = {
  metric_name: string;
  label: string;
  unit: "deg" | "ratio";
  level: RiskLevel;
  valid_ratio?: number;
  data_quality?: "sufficient" | "limited" | "insufficient";
  statistics?: {
    median?: number;
    maximum?: number;
    percentile_95?: number;
    percentile?: number;
    percentile_used?: number;
  };
  exposure?: {
    total_valid_duration_seconds?: number;
    moderate_duration_seconds?: number;
    high_duration_seconds?: number;
    critical_duration_seconds?: number;
    moderate_exposure_ratio?: number;
    high_exposure_ratio?: number;
    critical_exposure_ratio?: number;
  };
};

export type ReportKeyMoment = {
  source_frame_index?: number;
  output_frame_index?: number;
  timestamp_seconds?: number;
  metric_name: string;
  metric_label: string;
  area_id?: string;
  area_label?: string;
  value?: number;
  level: RiskLevel;
  quality?: number;
  reason: string;
};

export type AnalysisReport = {
  schema_version: "1.0";
  generated_by: "Ergonomia AI Report Engine";
  report_version: "analysis-report-v1.0";
  generated_at: string;
  analysis: {
    analysis_id: string;
    title: string;
    analyzed_frames: number;
    created_at?: string;
    source_file_name?: string;
    source_duration_seconds?: number;
    source_width?: number;
    source_height?: number;
  };
  processing: {
    pose_pipeline_version?: string;
    ergonomics_metrics_version: string;
    risk_engine_version: string;
    report_engine_version: string;
  };
  data_quality: {
    frame_count: number;
    valid_metric_ratio: number;
    insufficient_data: boolean;
    pose_presence_ratio?: number;
    pose_processed_frames?: number;
    pose_detected_frames?: number;
    invalid_metric_values?: number;
    rejection_reasons: Array<{
      reason: string;
      count: number;
    }>;
  };
  risk_summary: ReportRiskSummary;
  body_areas: ReportBodyArea[];
  metric_summary: ReportMetricSummary[];
  key_moments: ReportKeyMoment[];
  observations: string[];
  limitations: string[];
  disclaimer: string;
  holding_activity?: {
    external_load_known?: boolean;
    left?: ReportHandActivity;
    right?: ReportHandActivity;
    bimanual?: {
      likely_holding_seconds?: number;
      episode_count?: number;
    };
  };
  hand_activity?: AnalysisReport["holding_activity"];
  movement_features?: Record<string, ReportMovementFeature>;
  posture_duration?: Record<string, number | string | null>;
  pose_quality?: Record<string, unknown>;
};

export type ReportHandActivity = {
  valid_observation_seconds?: number;
  likely_holding_seconds?: number;
  static_holding_seconds?: number;
  longest_holding_seconds?: number;
  holding_ratio?: number;
  holding_episode_count?: number;
  holding_detected?: "likely" | "not_detected" | "unknown";
  unclassified_object_possible?: boolean;
  object_interactions?: Array<{
    object_class: string;
    holding_seconds: number;
    confidence: number | null;
  }>;
};

export type ReportMovementFeature = {
  valid_frames?: number;
  invalid_frames?: number;
  movement_range?: number;
  range_of_motion?: number;
  median_absolute_velocity?: number;
  percentile_95_absolute_velocity?: number;
  peak_absolute_velocity?: number;
  repetition_count?: number;
  cycle_count?: number;
  reversal_count?: number;
  cycles_per_minute?: number;
  longest_stable_posture_seconds?: number;
  valid_exposure_seconds?: number;
};

export type ReportSummary = {
  report_version: "analysis-report-v1.0";
  analysis_id: string;
  overall_level: RiskLevel;
  insufficient_data: boolean;
  valid_metric_ratio: number;
  dominant_zone: string | null;
  dominant_metric: string | null;
  key_moments_count: number;
  metric_count: number;
  profile_status: RiskProfileStatus;
};

export type ReportAnalysisMetadata = {
  report_path: string | null;
  report_version: string | null;
  report_summary: ReportSummary | null;
  report_completed_at: string | null;
  report_error_code: string | null;
  report_error_message: string | null;
  report_worker_id: string | null;
  report_started_at: string | null;
  report_attempts: number;
};
