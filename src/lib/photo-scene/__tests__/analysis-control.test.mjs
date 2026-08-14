import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { derivePhotoAnalysisUi, mergeSceneDetection } from "../analysis-control.ts";
import { emptySceneState } from "../schema.ts";

const now = Date.parse("2026-08-12T20:00:00Z");
const candidate = (id = "candidate-1", bbox = { x: .2, y: .2, width: .3, height: .2 }) => ({ id, source_class: "dining table", suggested_scene_type: "TABLE", bounding_box: bbox, confidence: .8, source: "YOLOX_X_COCO", status: "DETECTED" });
const detection = (candidates = [candidate()], suggestions = []) => ({ schema_version: "1.0", detection_version: "scene-detection-v0.2-beta.1", analysis_id: "analysis", source_image: { width: 1000, height: 800 }, candidates, dimension_suggestions: suggestions, limitations: [] });

test("photo analysis states cover initial, queue, processing, complete, failed and no detections", () => {
  assert.equal(derivePhotoAnalysisUi({ processingStage: null, detection: null, now }).status, "NOT_ANALYZED");
  assert.equal(derivePhotoAnalysisUi({ processingStage: "ready-for-scene-detection", detection: null, now }).status, "QUEUED");
  assert.equal(derivePhotoAnalysisUi({ processingStage: "scene-detection-processing", detection: null, heartbeatAt: "2026-08-12T19:59:50Z", now }).status, "ANALYZING");
  assert.equal(derivePhotoAnalysisUi({ processingStage: "scene-ready", detection: detection(), now }).status, "READY");
  assert.equal(derivePhotoAnalysisUi({ processingStage: "scene-ready", detection: detection([]), now }).status, "NO_DETECTIONS");
  assert.equal(derivePhotoAnalysisUi({ processingStage: "scene-detection-failed", detection: null, now }).status, "ERROR");
});

test("worker vertical direction remains a suggestion until user confirmation", () => {
  const result = mergeSceneDetection(emptySceneState(), { ...detection([]), perspective_evidence: { dominant_vertical_angle_deg: 84, dominant_horizontal_angle_deg: 2, vanishing_point: null, evidence_quality: "MEDIUM" } });
  assert.equal(result.calibration.verticalDirectionSource, "WORKER_SUGGESTED");
  assert.equal(result.calibration.verticalDirectionConfirmed, false);
  assert.ok(result.calibration.verticalDirection.y < 0);
});

test("stale processing and an offline worker enable a controlled retry", () => {
  const status = derivePhotoAnalysisUi({ processingStage: "scene-detection-processing", detection: null, heartbeatAt: "2026-08-12T19:55:00Z", workerStatus: "offline", now });
  assert.equal(status.status, "WORKER_OFFLINE");
  assert.equal(status.buttonEnabled, true);
  assert.equal(status.stalled, true);
});

test("a queue without activity becomes worker-offline even when remote health is unavailable", () => {
  const status = derivePhotoAnalysisUi({ processingStage: "ready-for-scene-detection", detection: null, updatedAt: "2026-08-12T19:55:00Z", now });
  assert.equal(status.status, "WORKER_OFFLINE");
  assert.equal(status.buttonEnabled, true);
});

test("reanalysis does not duplicate a matching confirmed detection", () => {
  const first = mergeSceneDetection(emptySceneState(), detection());
  first.objects[0] = { ...first.objects[0], status: "USER_CONFIRMED", name: "Mój stół" };
  const second = mergeSceneDetection(first, detection([candidate("candidate-new", { x: .205, y: .2, width: .3, height: .2 })]));
  assert.equal(second.objects.length, 1);
  assert.equal(second.objects[0].name, "Mój stół");
  assert.equal(second.objects[0].status, "USER_CONFIRMED");
});

test("reanalysis preserves user-rejected objects instead of restoring them", () => {
  const first = mergeSceneDetection(emptySceneState(), detection());
  first.objects[0] = { ...first.objects[0], status: "USER_REJECTED" };
  const second = mergeSceneDetection(first, detection([candidate("candidate-new")]));
  assert.equal(second.objects.length, 1);
  assert.equal(second.objects[0].status, "USER_REJECTED");
});

test("reanalysis preserves USER_MEASURED geometry and manual scene state", () => {
  const state = emptySceneState();
  state.objects.push({
    ...mergeSceneDetection(emptySceneState(), detection()).objects[0],
    id: "manual-table",
    status: "USER_MODIFIED",
    geometryMeasurements: [{ id: "manual-measure", objectId: "manual-table", name: "Blat", dimensionKey: "widthCm", valueCm: 120, unit: "cm", start: { x: .2, y: .2 }, end: { x: .5, y: .2 }, source: "USER_MEASURED", estimateStatus: "CONFIRMED", active: true, visible: true, locked: false, reason: null }],
  });
  state.humans.push({ id: "human-placeholder" });
  const merged = mergeSceneDetection(state, detection([candidate("new-table")]));
  assert.equal(merged.objects.length, 1);
  assert.equal(merged.objects[0].geometryMeasurements[0].source, "USER_MEASURED");
  assert.equal(merged.humans.length, 1);
});

test("suggestions are remapped to an existing object and deduplicated geometrically", () => {
  const suggestion = { id: "suggestion-1", object_id: "candidate-1", dimension_type: "widthCm", endpoints: { start: { x: .2, y: .2 }, end: { x: .5, y: .2 } }, source: "WORKER_GEOMETRY_HEURISTIC", estimated_value_cm: null, estimate_status: "UNKNOWN", evidence_quality: "MEDIUM", reason: "test" };
  const first = mergeSceneDetection(emptySceneState(), detection([candidate()], [suggestion]));
  first.objects[0] = { ...first.objects[0], id: "confirmed", status: "USER_CONFIRMED" };
  first.workerSuggestions = [];
  const second = mergeSceneDetection(first, detection([candidate("fresh")], [{ ...suggestion, id: "fresh-suggestion", object_id: "fresh" }]));
  const third = mergeSceneDetection(second, detection([candidate("fresh-again")], [{ ...suggestion, id: "another", object_id: "fresh-again" }]));
  assert.equal(third.objects.length, 1);
  assert.equal(third.workerSuggestions.length, 1);
  assert.equal(third.workerSuggestions[0].object_id, "confirmed");
});

test("reanalysis RPC preserves the queue contract and accepts only owned photo scenes", () => {
  const sql = readFileSync(new URL("../../../../supabase/migrations/20260812190000_enable_photo_scene_reanalysis.sql", import.meta.url), "utf8").toLowerCase();
  assert.match(sql, /create or replace function public\.retry_scene_detection\(p_analysis_id uuid\)/);
  assert.match(sql, /analysis_type = 'photo_scene'/);
  assert.match(sql, /user_id = \(select auth\.uid\(\)\).*public\.is_admin\(\)/s);
  assert.match(sql, /processing_stage in \('scene-detection-failed', 'scene-ready'\)/);
  assert.match(sql, /interval '2 minutes'/);
  assert.match(sql, /grant execute on function public\.retry_scene_detection\(uuid\) to authenticated/);
  assert.doesNotMatch(sql, /detection_result\s*=/);
  assert.doesNotMatch(sql, /scene_state\s*=/);
});
