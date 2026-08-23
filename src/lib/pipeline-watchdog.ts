import type { PipelineHealth } from "@/lib/pipeline-health";
import type { PipelineWatchdogCode } from "@/config/pipeline-alerts";

type AnalysisWatchdogInput = {
  id: string;
  status: string;
  processing_stage: string | null;
  updated_at: string | null;
  heartbeat_at?: string | null;
  error_code?: string | null;
};

const queuedStages = new Set(["queued", "ready-for-ai", "ready-for-ergonomics", "ready-for-risk-assessment", "ready-for-report"]);
const activeStages = new Set([
  "claimed", "claimed-for-preprocessing", "downloading-source", "preprocessing-video", "saving-preprocessing-results",
  "pose-claimed", "downloading-for-pose", "downloading-for-pose-v3", "initializing-pose-inference", "pose-inference",
  "pose-inference-active-segment-v3", "pose-v3-rendering-validated-results", "uploading-pose-results-v3", "saving-pose-results-v3",
  "pose-v6-collecting-body-and-hands", "pose-v6-temporal-reconstruction", "pose-v6-rendering-persistent-skeleton",
  "downloading-for-pose-v6", "pose-inference-active-segment-v6", "uploading-pose-results-v6", "saving-pose-results-v6",
  "ergonomics-processing", "risk-processing", "report-processing",
]);

function ageSeconds(value: string | null | undefined, now: number) {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? Math.max(0, (now - parsed) / 1000) : Number.POSITIVE_INFINITY;
}

export function classifyPipelineWatchdog(
  analysis: AnalysisWatchdogInput,
  health: PipelineHealth,
  now = Date.now(),
): PipelineWatchdogCode {
  if (analysis.status === "completed" || analysis.processing_stage === "completed") return "COMPLETED";
  if (analysis.status === "failed" || analysis.processing_stage?.endsWith("-failed")) return "FAILED";
  if (health.status === "crash_loop") return "CRASH_LOOP";
  if (health.status === "degraded") return "DEGRADED";
  const heartbeatFresh = ageSeconds(health.last_heartbeat_at, now) <= 15;
  const stage = analysis.processing_stage ?? analysis.status;
  const activeAnalysisHeartbeat = activeStages.has(stage) && ageSeconds(analysis.heartbeat_at, now) <= 120;
  if (
    health.health_persistence === "degraded"
    || health.health_read_status === "cached"
  ) return "HEALTH_PERSISTENCE_DEGRADED";
  if (health.status === "unknown") {
    const failureIsNew = ageSeconds(health.health_unavailable_since, now) <= 15;
    return failureIsNew || activeAnalysisHeartbeat
      ? "HEALTH_PERSISTENCE_DEGRADED"
      : "WORKER_OFFLINE";
  }
  if (!heartbeatFresh) {
    return activeAnalysisHeartbeat ? "HEALTH_PERSISTENCE_DEGRADED" : "WORKER_OFFLINE";
  }
  if (health.status === "offline") return "WORKER_OFFLINE";
  if (activeStages.has(stage)) {
    if (ageSeconds(analysis.heartbeat_at, now) <= 120) return "PROCESSING";
    const pipelineOwnsAnalysis = health.pipeline_pid !== null && health.analysis_id === analysis.id;
    const progressFresh = ageSeconds(health.last_progress_at, now) <= 120;
    return pipelineOwnsAnalysis && progressFresh ? "PROCESSING" : "STALLED";
  }
  if (queuedStages.has(stage) || analysis.status === "queued") {
    if (health.analysis_id && health.analysis_id !== analysis.id) return "WORKER_BUSY";
    const waiting = ageSeconds(analysis.updated_at, now);
    return waiting > 60 ? "CLAIM_DELAY" : waiting > 30 ? "QUEUE_WAITING" : "QUEUE_OK";
  }
  return "QUEUE_OK";
}
