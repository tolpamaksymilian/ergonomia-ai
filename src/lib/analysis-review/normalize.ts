import { classifyDeviation, METRIC_DEFINITIONS, METRIC_NAMES } from "./config.ts";
import { normalizeAssessment } from "./assessment.ts";
import { rankAndDeduplicateKeyMoments } from "./key-moments.ts";
import type {
  AnalysisReviewModel,
  BimanualReview,
  HandReview,
  HoldingEpisode,
  KeyMoment,
  MetricPoint,
  MetricStatistics,
  NormalizeAnalysisInput,
  QualityReview,
  ReviewMetric,
  ReviewMetricName,
  RiskReview,
  TimelineSegment,
  UnknownRecord,
} from "./schemas.ts";
import { isRecord } from "./schemas.ts";
import { downsampleMetricPoints, mergeTimelineSegments, metricPointsToSegments } from "./timeline.ts";

const POSTURE_TIMELINE_METRICS: readonly ReviewMetricName[] = [
  "trunk_inclination_deg",
  "neck_flexion_deg",
  "left_upper_arm_elevation_deg",
  "right_upper_arm_elevation_deg",
  "left_wrist_flexion_deg",
  "right_wrist_flexion_deg",
];

export function normalizeAnalysisReview(input: NormalizeAnalysisInput): AnalysisReviewModel {
  const pose = recordOrNull(input.pose);
  const ergonomics = recordOrNull(input.ergonomics);
  const risk = recordOrNull(input.risk);
  const report = recordOrNull(input.report);
  const assessmentDocument = recordOrNull(input.assessment);
  const assessment = normalizeAssessment(assessmentDocument);
  const poseSummary = child(pose, "summary");
  const poseSource = child(pose, "source");
  const metrics = normalizeMetrics(ergonomics);
  const holding = normalizeHolding(ergonomics, poseSummary, pose);
  const quality = normalizeQuality(ergonomics, poseSummary);
  const hands = {
    left: { ...holding.left, validRatio: holding.left.validRatio ?? quality.leftHandValidRatio },
    right: { ...holding.right, validRatio: holding.right.validRatio ?? quality.rightHandValidRatio },
    bimanual: holding.bimanual,
  };
  const riskReview = normalizeRisk(risk, report);
  const durationSeconds = firstNumber(
    child(pose, "active_segment")?.output_duration_seconds,
    poseSource?.duration_seconds,
    report && child(report, "analysis")?.source_duration_seconds,
    input.fallbackDurationSeconds,
    maximumMetricTime(metrics),
  );
  const timeline = [
    ...buildTimeline(metrics, pose, holding),
    ...assessment.candidates.map((candidate) => ({
      id: `assessment-${candidate.id}`,
      layer: "assessment" as const,
      track: "assessment-candidates",
      label: "Pozycja RULA/REBA",
      start: candidate.timestamp,
      end: candidate.timestamp,
      quality: candidate.quality,
      description: "Reprezentatywna pozycja wybrana do oceny metodą.",
    })),
  ];
  const keyMoments = buildKeyMoments(metrics, holding, timeline);
  const compactMetrics = compactMetricSeries(metrics);
  const limitations = uniqueStrings([
    ...textArray(report?.limitations),
    ...textArray(risk?.limitations),
    ...textArray(ergonomics?.quality_limitations),
    ...assessment.limitations,
  ]);

  return {
    analysisId: input.analysisId,
    poseSchemaVersion: text(pose?.schema_version) ?? text(pose?.pose_schema_version),
    poseVersion: text(pose?.pose_version) ?? text(pose?.pipeline_version),
    workerVersion: text(pose?.worker_version),
    metricsVersion: text(ergonomics?.metrics_version),
    reportVersion: text(report?.report_version),
    durationSeconds,
    fps: firstNumber(poseSource?.fps),
    processedFrames: integer(poseSummary?.processed_frames) ?? integer(input.fallbackProcessedFrames),
    metrics: compactMetrics,
    timeline,
    hands,
    quality,
    risk: riskReview,
    assessment,
    keyMoments,
    limitations,
    availableSources: {
      pose: pose !== null,
      ergonomics: ergonomics !== null,
      risk: risk !== null,
      report: report !== null,
      assessment: assessmentDocument !== null,
    },
  };
}

function normalizeMetrics(document: UnknownRecord | null): Record<ReviewMetricName, ReviewMetric> {
  const frames = array(document?.frames);
  const summary = child(document, "summary");
  const movement = child(document, "movement_features");
  const output = {} as Record<ReviewMetricName, ReviewMetric>;
  for (const name of METRIC_NAMES) {
    const definition = METRIC_DEFINITIONS[name];
    const fullPoints: MetricPoint[] = [];
    for (const [fallbackIndex, rawFrame] of frames.entries()) {
      if (!isRecord(rawFrame)) continue;
      const rawMetric = child(child(rawFrame, "metrics"), name);
      const rawValue = rawMetric?.value;
      const value = number(rawValue);
      const explicitlyValid = rawMetric?.valid === true;
      const time = firstNumber(rawFrame.source_timestamp_seconds, rawFrame.timestamp, rawFrame.output_timestamp_seconds);
      if (time === null) continue;
      const valid = explicitlyValid && value !== null;
      fullPoints.push({
        time,
        value: valid ? value : null,
        quality: ratio(rawMetric?.quality),
        valid,
        band: valid ? classifyDeviation(name, value) : "unknown",
        sourceFrameIndex: integer(rawFrame.source_frame_index),
        outputFrameIndex: integer(rawFrame.output_frame_index) ?? fallbackIndex,
        provenance: poseTimelineState(rawMetric?.timeline_state),
        usability: poseUsability(rawMetric?.usability),
      });
    }
    const rawSummary = child(summary, name);
    const rawMovement = child(movement, name);
    output[name] = {
      name,
      label: definition.label,
      shortLabel: definition.shortLabel,
      unit: definition.unit,
      group: definition.group,
      bodyArea: definition.bodyArea,
      points: fullPoints,
      statistics: normalizeMetricStatistics(rawSummary, rawMovement),
    };
  }
  return output;
}

function normalizeMetricStatistics(summary: UnknownRecord | null, movement: UnknownRecord | null): MetricStatistics {
  return {
    validFrames: integer(summary?.valid_frames),
    invalidFrames: integer(summary?.invalid_frames),
    validRatio: ratio(summary?.valid_ratio),
    median: number(summary?.median),
    minimum: number(summary?.minimum),
    maximum: number(summary?.maximum),
    percentile95: number(summary?.percentile_95),
    validExposureSeconds: nonNegative(movement?.valid_exposure_seconds),
    rangeOfMotion: nonNegative(movement?.range_of_motion ?? movement?.movement_range),
    medianVelocity: nonNegative(movement?.median_absolute_velocity),
    peakVelocity: nonNegative(movement?.peak_absolute_velocity),
    cycleCount: integer(movement?.cycle_count),
    longestStablePostureSeconds: nonNegative(movement?.longest_stable_posture_seconds),
  };
}

function normalizeHolding(
  ergonomics: UnknownRecord | null,
  poseSummary: UnknownRecord | null,
  pose: UnknownRecord | null,
): { left: HandReview; right: HandReview; bimanual: BimanualReview } {
  const ergonomicsActivity = child(ergonomics, "hand_activity") ?? child(ergonomics, "holding_activity");
  const source = ergonomicsActivity ?? child(poseSummary, "holding");
  const left = normalizeHand("left", child(source, "left"));
  const right = normalizeHand("right", child(source, "right"));
  const bimanualRaw = child(source, "bimanual");
  const bimanualEpisodes = bimanualEpisodesFromFrames(array(pose?.frames));
  return {
    left,
    right,
    bimanual: {
      holdingSeconds: nonNegative(bimanualRaw?.likely_holding_seconds),
      episodeCount: integer(bimanualRaw?.episode_count),
      episodes: bimanualEpisodes,
    },
  };
}

function normalizeHand(side: "left" | "right", source: UnknownRecord | null): HandReview {
  const episodes = array(source?.episodes).flatMap((item, index) => {
    if (!isRecord(item)) return [];
    const start = firstNumber(item.start_time, item.start_seconds);
    const end = firstNumber(item.end_time, item.end_seconds);
    if (start === null || end === null || start < 0 || end < start) return [];
    return [{
      id: `${side}-${index}-${start}`,
      side,
      start,
      end,
      duration: nonNegative(item.duration_seconds) ?? end - start,
      confidence: ratio(item.confidence),
      objectClass: text(item.known_object_class) ?? text(item.object_class),
    } satisfies HoldingEpisode];
  });
  return {
    side,
    validObservationSeconds: nonNegative(source?.valid_observation_seconds ?? source?.observed_time_seconds),
    holdingSeconds: nonNegative(source?.likely_holding_seconds),
    holdingRatio: ratio(source?.holding_ratio) ?? percentageRatio(source?.holding_percentage_of_valid_observation),
    longestHoldingSeconds: nonNegative(source?.longest_holding_seconds ?? source?.max_hold_duration_seconds),
    staticHoldingSeconds: nonNegative(source?.static_holding_seconds),
    episodeCount: integer(source?.holding_episode_count) ?? (source ? episodes.length : null),
    graspReleaseCycles: integer(source?.grasp_release_cycles),
    pinchCycles: integer(source?.pinch_cycles),
    validRatio: ratio(source?.valid_ratio),
    episodes,
  };
}

function normalizeQuality(ergonomics: UnknownRecord | null, poseSummary: UnknownRecord | null): QualityReview {
  const sourceSummary = child(ergonomics, "source_quality_summary") ?? poseSummary;
  const tracking = child(sourceSummary, "tracking");
  const quality = child(sourceSummary, "quality");
  const leftHand = child(sourceSummary, "left_hand") ?? child(child(sourceSummary, "hands"), "left");
  const rightHand = child(sourceSummary, "right_hand") ?? child(child(sourceSummary, "hands"), "right");
  return {
    bodyValidRatio: ratio(tracking?.valid_body_frame_ratio) ?? ratio(sourceSummary?.presence_ratio),
    leftHandValidRatio: ratio(leftHand?.valid_ratio),
    rightHandValidRatio: ratio(rightHand?.valid_ratio),
    outOfFrameRatio: ratio(tracking?.out_of_frame_ratio),
    trackLosses: integer(tracking?.track_loss_count ?? tracking?.losses),
    reacquisitions: integer(tracking?.reacquisition_count ?? tracking?.reacquisitions),
    meanFrameQuality: ratio(quality?.mean_frame_quality),
    warnings: uniqueStrings(textArray(quality?.warning_codes)),
  };
}

function normalizeRisk(risk: UnknownRecord | null, report: UnknownRecord | null): RiskReview {
  const overall = child(risk, "overall");
  const profile = child(risk, "profile");
  const reportRisk = child(report, "risk_summary");
  const reportProfile = child(reportRisk, "profile");
  const level = riskLevel(overall?.overall_level) ?? riskLevel(reportRisk?.overall_level);
  return {
    level,
    profileName: text(profile?.profile_name) ?? text(reportProfile?.profile_name),
    profileVersion: text(profile?.profile_version) ?? text(reportProfile?.profile_version),
    dominantMetrics: uniqueStrings([...textArray(reportRisk?.dominant_metrics), ...riskDominantMetrics(risk)]),
    dominantZones: uniqueStrings([...textArray(overall?.highest_risk_zones), ...textArray(reportRisk?.dominant_zones)]),
    decisionReasons: textArray(overall?.decision_reasons),
  };
}

function buildTimeline(
  metrics: Record<ReviewMetricName, ReviewMetric>,
  pose: UnknownRecord | null,
  holding: { left: HandReview; right: HandReview; bimanual: BimanualReview },
): TimelineSegment[] {
  const segments: TimelineSegment[] = [];
  for (const name of POSTURE_TIMELINE_METRICS) {
    segments.push(...metricPointsToSegments(metrics[name].points, name, metrics[name].shortLabel));
  }
  for (const episode of [...holding.left.episodes, ...holding.right.episodes, ...holding.bimanual.episodes]) {
    segments.push({
      id: `holding-${episode.id}`,
      layer: "holding",
      track: episode.side,
      label: episode.side === "left" ? "Lewa dłoń" : episode.side === "right" ? "Prawa dłoń" : "Oburącz",
      start: episode.start,
      end: episode.end,
      quality: episode.confidence,
      description: episode.objectClass ?? undefined,
    });
  }
  segments.push(...poseFrameSegments(array(pose?.frames)));
  return segments.sort((a, b) => a.start - b.start || a.layer.localeCompare(b.layer));
}

function poseFrameSegments(frames: unknown[]): TimelineSegment[] {
  const raw: Array<Omit<TimelineSegment, "id">> = [];
  let fallbackStep = 1 / 30;
  let previousTime: number | null = null;
  for (const item of frames) {
    if (!isRecord(item)) continue;
    const time = firstNumber(item.source_timestamp_seconds, item.output_timestamp_seconds);
    if (time === null) continue;
    if (previousTime !== null && time > previousTime) fallbackStep = time - previousTime;
    previousTime = time;
    const end = time + fallbackStep;
    const trackingState = text(item.tracking_state) ?? text(child(item, "tracking")?.state);
    if (trackingState && ["LOST", "REACQUIRING", "OUT_OF_FRAME"].includes(trackingState.toUpperCase())) {
      raw.push({ layer: trackingState.toUpperCase() === "REACQUIRING" ? "events" : "quality", track: "tracking", label: trackingState, start: time, end });
    }
    const frameQuality = child(item, "frame_quality");
    const frameState = text(frameQuality?.state);
    if (frameState && ["POOR", "INVALID"].includes(frameState.toUpperCase())) {
      raw.push({ layer: "quality", track: "body", label: "Niska jakość sylwetki", start: time, end, quality: ratio(frameQuality?.score) });
    }
    for (const reason of textArray(frameQuality?.reasons)) {
      if (["HIGH_MOTION_BLUR", "HAND_OCCLUSION", "LOW_BODY_COVERAGE"].includes(reason)) {
        raw.push({ layer: "quality", track: reason, label: reason, start: time, end, quality: ratio(frameQuality?.score) });
      }
    }
    for (const side of ["left", "right"] as const) {
      const hand = child(item, `${side}_hand`);
      const graph = child(hand, "graph_v2");
      const grip = child(hand, "grip");
      const gripState = text(grip?.grip_state);
      if (gripState && gripState !== "UNKNOWN") {
        raw.push({ layer: "hands", track: side, label: gripState, start: time, end, quality: ratio(graph?.quality) });
      }
    }
  }
  return mergeTimelineSegments(raw, Math.max(0.12, fallbackStep * 1.5));
}

function buildKeyMoments(
  metrics: Record<ReviewMetricName, ReviewMetric>,
  holding: { left: HandReview; right: HandReview; bimanual: BimanualReview },
  timeline: TimelineSegment[],
): KeyMoment[] {
  const candidates: KeyMoment[] = [];
  const keyMetricNames: readonly ReviewMetricName[] = [
    "trunk_inclination_deg", "neck_flexion_deg", "left_upper_arm_elevation_deg",
    "right_upper_arm_elevation_deg", "left_wrist_flexion_deg", "right_wrist_flexion_deg",
  ];
  for (const name of keyMetricNames) {
    const metric = metrics[name];
    const valid = metric.points.filter((point) => point.valid && point.value !== null);
    const selected = valid.sort((a, b) => deviationMagnitude(name, b.value ?? 0) - deviationMagnitude(name, a.value ?? 0) || (b.quality ?? 0) - (a.quality ?? 0))[0];
    if (!selected || selected.value === null) continue;
    const severity = { neutral: 0, mild: 1, elevated: 2, strong: 3, unknown: 0 }[selected.band];
    candidates.push({
      id: `metric-${name}`,
      category: "posture",
      time: selected.time,
      title: `Największe ${metric.label.toLocaleLowerCase("pl-PL")}`,
      description: `${metric.shortLabel}: ${Math.round(selected.value)}° (${selected.band === "unknown" ? "brak oceny odchylenia" : "geometryczne odchylenie"}).`,
      value: selected.value,
      unit: metric.unit,
      bodyArea: metric.bodyArea,
      rank: 30 + severity * 18 + (selected.quality ?? 0) * 8,
      quality: selected.quality,
    });
  }
  for (const episode of [...holding.left.episodes, ...holding.right.episodes, ...holding.bimanual.episodes]) {
    candidates.push({
      id: `episode-${episode.id}`,
      category: "holding",
      time: episode.start,
      title: episode.side === "bimanual" ? "Chwyt oburącz" : `Dłuższy chwyt — ${episode.side === "left" ? "lewa" : "prawa"} dłoń`,
      description: `Epizod trzymania trwał ${episode.duration.toFixed(1)} s${episode.objectClass ? `; obiekt: ${episode.objectClass}` : "; przedmiot nieokreślony"}.`,
      value: episode.duration,
      unit: "seconds",
      bodyArea: episode.side === "bimanual" ? "hands" : `${episode.side}_hand`,
      rank: 50 + Math.min(25, episode.duration * 2) + (episode.side === "bimanual" ? 12 : 0) + (episode.confidence ?? 0) * 8,
      quality: episode.confidence,
    });
  }
  for (const segment of timeline.filter((item) => item.layer === "quality" || item.layer === "events")) {
    const duration = segment.end - segment.start;
    candidates.push({
      id: `quality-${segment.id}`,
      category: "quality",
      time: segment.start,
      title: segment.layer === "events" ? "Ponowne podjęcie śledzenia" : "Ograniczona jakość danych",
      description: segment.label,
      value: duration,
      unit: "seconds",
      bodyArea: null,
      rank: 35 + Math.min(20, duration * 4) + (segment.layer === "events" ? 8 : 0),
      quality: segment.quality ?? null,
    });
  }
  return rankAndDeduplicateKeyMoments(candidates, { minimumGapSeconds: 0.75, limit: 8 });
}

function bimanualEpisodesFromFrames(frames: unknown[]): HoldingEpisode[] {
  const samples = frames.flatMap((item) => {
    if (!isRecord(item)) return [];
    const time = firstNumber(item.source_timestamp_seconds, item.output_timestamp_seconds);
    const holding = child(item, "holding");
    return time !== null ? [{ time, active: holding?.bimanual_candidate === true }] : [];
  });
  const episodes: HoldingEpisode[] = [];
  let start: number | null = null;
  for (let index = 0; index <= samples.length; index += 1) {
    const sample = samples[index];
    if (sample?.active && start === null) start = sample.time;
    if ((!sample?.active || index === samples.length) && start !== null) {
      const previous = samples[index - 1];
      const end = previous?.time ?? start;
      episodes.push({ id: `bimanual-${episodes.length}-${start}`, side: "bimanual", start, end, duration: Math.max(0, end - start), confidence: null, objectClass: null });
      start = null;
    }
  }
  return episodes;
}

function maximumMetricTime(metrics: Record<ReviewMetricName, ReviewMetric>): number | null {
  const values = METRIC_NAMES.flatMap((name) => metrics[name].points.map((point) => point.time));
  return values.length ? Math.max(...values) : null;
}

function compactMetricSeries(metrics: Record<ReviewMetricName, ReviewMetric>): Record<ReviewMetricName, ReviewMetric> {
  const output = {} as Record<ReviewMetricName, ReviewMetric>;
  for (const name of METRIC_NAMES) {
    output[name] = { ...metrics[name], points: downsampleMetricPoints(metrics[name].points) };
  }
  return output;
}

function deviationMagnitude(name: ReviewMetricName, value: number): number {
  const center = METRIC_DEFINITIONS[name].deviation?.center ?? 0;
  return Math.abs(value - center);
}

function riskDominantMetrics(risk: UnknownRecord | null): string[] {
  const metrics = child(risk, "metrics");
  if (!metrics) return [];
  return Object.entries(metrics)
    .flatMap(([name, value]) => isRecord(value) && number(value.weighted_score) !== null ? [{ name, score: number(value.weighted_score) ?? 0 }] : [])
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
    .slice(0, 5)
    .map((item) => item.name);
}

function riskLevel(value: unknown): RiskReview["level"] {
  return typeof value === "string" && ["low", "moderate", "high", "critical", "insufficient_data"].includes(value)
    ? value as RiskReview["level"]
    : null;
}

function poseTimelineState(value: unknown): MetricPoint["provenance"] {
  return typeof value === "string" && [
    "MEASURED", "REFINED_MODEL", "TEMPORALLY_RECONSTRUCTED", "FLOW_TRACKED",
    "KINEMATICALLY_INFERRED", "LOW_CONFIDENCE_BUT_USABLE", "NOT_VISIBLE", "NO_DATA",
  ].includes(value) ? value as MetricPoint["provenance"] : null;
}

function poseUsability(value: unknown): MetricPoint["usability"] {
  return typeof value === "string" && [
    "fully_usable", "usable_with_reconstruction", "usable_for_timeline_only", "insufficient",
  ].includes(value) ? value as MetricPoint["usability"] : null;
}

function recordOrNull(value: unknown): UnknownRecord | null { return isRecord(value) ? value : null; }
function child(value: UnknownRecord | null | undefined, key: string): UnknownRecord | null { const result = value?.[key]; return isRecord(result) ? result : null; }
function array(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }
function text(value: unknown): string | null { return typeof value === "string" && value.trim() ? value.trim() : null; }
function number(value: unknown): number | null { return typeof value === "number" && Number.isFinite(value) ? value : null; }
function nonNegative(value: unknown): number | null { const result = number(value); return result !== null && result >= 0 ? result : null; }
function integer(value: unknown): number | null { const result = number(value); return result !== null && Number.isInteger(result) && result >= 0 ? result : null; }
function ratio(value: unknown): number | null { const result = number(value); return result !== null && result >= 0 && result <= 1 ? result : null; }
function percentageRatio(value: unknown): number | null { const result = number(value); return result !== null && result >= 0 && result <= 100 ? result / 100 : null; }
function firstNumber(...values: unknown[]): number | null { for (const value of values) { const result = number(value); if (result !== null) return result; } return null; }
function textArray(value: unknown): string[] { return array(value).flatMap((item) => text(item) ?? []); }
function uniqueStrings(values: string[]): string[] { return [...new Set(values)]; }
