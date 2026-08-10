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
  if (!heartbeatFresh || health.status === "offline" || health.status === "unknown") return "WORKER_OFFLINE";
  const stage = analysis.processing_stage ?? analysis.status;
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
