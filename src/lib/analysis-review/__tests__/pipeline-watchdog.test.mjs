import assert from "node:assert/strict";
import test from "node:test";

import { classifyPipelineWatchdog } from "../../pipeline-watchdog.ts";

const now = Date.parse("2026-08-10T12:00:00Z");
const health = {
  schema_version: "1.0", supervisor_version: "test", status: "online", state: "idle",
  supervisor_pid: 1, pipeline_pid: 2, started_at: null, last_heartbeat_at: "2026-08-10T11:59:55Z",
  analysis_id: null, stage: null, last_progress_at: null, restart_count: 0,
  preflight_status: "OK", preflight: [], last_error: null,
  health_persistence: "healthy", health_read_status: "current", health_unavailable_since: null,
};
const analysis = { id: "a", status: "queued", processing_stage: "queued", updated_at: "2026-08-10T11:59:50Z" };

test("fresh worker keeps a new queued analysis healthy", () => {
  assert.equal(classifyPipelineWatchdog(analysis, health, now), "QUEUE_OK");
});

test("stale heartbeat means worker offline", () => {
  assert.equal(classifyPipelineWatchdog(analysis, { ...health, last_heartbeat_at: "2026-08-10T11:58:00Z" }, now), "WORKER_OFFLINE");
});

test("fresh heartbeat prevents long Pose from being treated as stalled", () => {
  const pose = { ...analysis, status: "processing", processing_stage: "pose-inference-active-segment-v3", updated_at: "2026-08-10T11:50:00Z", heartbeat_at: "2026-08-10T11:59:10Z" };
  assert.equal(classifyPipelineWatchdog(pose, { ...health, analysis_id: "a", last_progress_at: "2026-08-10T11:50:00Z" }, now), "PROCESSING");
});

test("live supervisor does not hide a stalled claimed stage", () => {
  const pose = { ...analysis, status: "processing", processing_stage: "pose-inference-active-segment-v3", updated_at: "2026-08-10T11:50:00Z", heartbeat_at: "2026-08-10T11:55:00Z" };
  assert.equal(classifyPipelineWatchdog(pose, { ...health, analysis_id: "a", last_progress_at: "2026-08-10T11:55:00Z" }, now), "STALLED");
});

test("worker busy on a different analysis is explicit", () => {
  const waiting = { ...analysis, updated_at: "2026-08-10T11:58:00Z" };
  assert.equal(classifyPipelineWatchdog(waiting, { ...health, analysis_id: "other" }, now), "WORKER_BUSY");
});

test("degraded preflight is exposed while supervisor heartbeat stays available", () => {
  assert.equal(classifyPipelineWatchdog(analysis, { ...health, status: "degraded", state: "preflight_error" }, now), "DEGRADED");
});

test("process control cannot be inferred from client health data", () => {
  assert.equal("secret" in health, false);
  assert.equal("control_allowed" in health, false);
});

test("a two-second heartbeat delay stays inside the normal grace period", () => {
  assert.equal(classifyPipelineWatchdog(analysis, { ...health, last_heartbeat_at: "2026-08-10T11:59:58Z" }, now), "QUEUE_OK");
});

test("fresh database worker heartbeat distinguishes persistence degradation from offline", () => {
  const pose = { ...analysis, status: "processing", processing_stage: "pose-v6-temporal-reconstruction", heartbeat_at: "2026-08-10T11:59:20Z" };
  assert.equal(
    classifyPipelineWatchdog(pose, { ...health, last_heartbeat_at: "2026-08-10T11:58:00Z" }, now),
    "HEALTH_PERSISTENCE_DEGRADED",
  );
});

test("temporary unreadable health is degraded before it becomes offline", () => {
  const unavailable = { ...health, status: "unknown", last_heartbeat_at: null, health_persistence: "unknown", health_read_status: "unavailable", health_unavailable_since: "2026-08-10T11:59:55Z" };
  assert.equal(classifyPipelineWatchdog(analysis, unavailable, now), "HEALTH_PERSISTENCE_DEGRADED");
  assert.equal(classifyPipelineWatchdog(analysis, { ...unavailable, health_unavailable_since: "2026-08-10T11:58:00Z" }, now), "WORKER_OFFLINE");
});
