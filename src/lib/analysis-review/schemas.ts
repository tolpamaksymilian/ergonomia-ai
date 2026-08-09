export type UnknownRecord = Record<string, unknown>;

export type DeviationBand =
  | "neutral"
  | "mild"
  | "elevated"
  | "strong"
  | "unknown";

export type ReviewMetricName =
  | "trunk_inclination_deg"
  | "neck_flexion_deg"
  | "left_upper_arm_elevation_deg"
  | "right_upper_arm_elevation_deg"
  | "left_elbow_flexion_deg"
  | "right_elbow_flexion_deg"
  | "left_forearm_inclination_deg"
  | "right_forearm_inclination_deg"
  | "left_wrist_flexion_deg"
  | "right_wrist_flexion_deg"
  | "left_hand_closure_ratio"
  | "right_hand_closure_ratio"
  | "left_pinch_distance_ratio"
  | "right_pinch_distance_ratio";

export type MetricPoint = {
  time: number;
  value: number | null;
  quality: number | null;
  valid: boolean;
  band: DeviationBand;
  sourceFrameIndex: number | null;
  outputFrameIndex: number | null;
};

export type MetricStatistics = {
  validFrames: number | null;
  invalidFrames: number | null;
  validRatio: number | null;
  median: number | null;
  minimum: number | null;
  maximum: number | null;
  percentile95: number | null;
  validExposureSeconds: number | null;
  rangeOfMotion: number | null;
  medianVelocity: number | null;
  peakVelocity: number | null;
  cycleCount: number | null;
  longestStablePostureSeconds: number | null;
};

export type ReviewMetric = {
  name: ReviewMetricName;
  label: string;
  shortLabel: string;
  unit: "deg" | "ratio";
  group: string;
  bodyArea: string;
  points: MetricPoint[];
  statistics: MetricStatistics;
};

export type TimelineSegment = {
  id: string;
  layer: "posture" | "hands" | "holding" | "quality" | "events";
  track: string;
  label: string;
  start: number;
  end: number;
  band?: DeviationBand;
  quality?: number | null;
  description?: string;
};

export type HoldingEpisode = {
  id: string;
  side: "left" | "right" | "bimanual";
  start: number;
  end: number;
  duration: number;
  confidence: number | null;
  objectClass: string | null;
};

export type HandReview = {
  side: "left" | "right";
  validObservationSeconds: number | null;
  holdingSeconds: number | null;
  holdingRatio: number | null;
  longestHoldingSeconds: number | null;
  staticHoldingSeconds: number | null;
  episodeCount: number | null;
  graspReleaseCycles: number | null;
  pinchCycles: number | null;
  validRatio: number | null;
  episodes: HoldingEpisode[];
};

export type BimanualReview = {
  holdingSeconds: number | null;
  episodeCount: number | null;
  episodes: HoldingEpisode[];
};

export type QualityGrade = "good" | "acceptable" | "poor" | "limited";

export type QualityReview = {
  bodyValidRatio: number | null;
  leftHandValidRatio: number | null;
  rightHandValidRatio: number | null;
  outOfFrameRatio: number | null;
  trackLosses: number | null;
  reacquisitions: number | null;
  meanFrameQuality: number | null;
  warnings: string[];
};

export type KeyMomentCategory = "posture" | "hands" | "holding" | "quality";

export type KeyMoment = {
  id: string;
  category: KeyMomentCategory;
  time: number;
  title: string;
  description: string;
  value: number | null;
  unit: "deg" | "ratio" | "seconds" | null;
  bodyArea: string | null;
  rank: number;
  quality: number | null;
};

export type RiskReview = {
  level: "low" | "moderate" | "high" | "critical" | "insufficient_data" | null;
  profileName: string | null;
  profileVersion: string | null;
  dominantMetrics: string[];
  dominantZones: string[];
  decisionReasons: string[];
};

export type AnalysisReviewModel = {
  analysisId: string;
  poseSchemaVersion: string | null;
  poseVersion: string | null;
  workerVersion: string | null;
  metricsVersion: string | null;
  reportVersion: string | null;
  durationSeconds: number | null;
  fps: number | null;
  processedFrames: number | null;
  metrics: Record<ReviewMetricName, ReviewMetric>;
  timeline: TimelineSegment[];
  hands: {
    left: HandReview;
    right: HandReview;
    bimanual: BimanualReview;
  };
  quality: QualityReview;
  risk: RiskReview;
  keyMoments: KeyMoment[];
  limitations: string[];
  availableSources: {
    pose: boolean;
    ergonomics: boolean;
    risk: boolean;
    report: boolean;
  };
};

export type NormalizeAnalysisInput = {
  analysisId: string;
  pose: unknown;
  ergonomics: unknown;
  risk: unknown;
  report: unknown;
  fallbackDurationSeconds?: number | null;
  fallbackProcessedFrames?: number | null;
};

export function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
