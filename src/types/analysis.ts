export type AnalysisProcessingStage =
  | "queued"
  | "ready-for-ai"
  | "pose-claimed"
  | "ready-for-ergonomics"
  | "ergonomics-processing"
  | "ergonomics-failed"
  | "ready-for-risk-assessment";

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
