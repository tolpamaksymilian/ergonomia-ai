import assert from "node:assert/strict";
import test from "node:test";

import { normalizeAnalysisReview } from "../normalize.ts";

const metricResult = (value, valid = true) => ({ value, valid, quality: valid ? 0.9 : 0, rejection_reason: valid ? null : "missing_keypoint" });
const ergonomics = {
  schema_version: "1.0",
  metrics_version: "ergonomics-metrics-v1.0",
  summary: { trunk_inclination_deg: { valid_frames: 1, invalid_frames: 1, valid_ratio: 0.5, median: 12, minimum: 12, maximum: 12, percentile_95: 12 } },
  movement_features: { trunk_inclination_deg: { range_of_motion: 0, valid_exposure_seconds: 0.04, cycle_count: 0 } },
  frames: [
    { timestamp: 0, metrics: { trunk_inclination_deg: metricResult(12) } },
    { timestamp: 0.04, metrics: { trunk_inclination_deg: metricResult(null, false) } },
  ],
};

for (const schema of ["3.0", "3.1", "4.0", "5.0", "5.1", "6.0"]) {
  test(`normalizer accepts Pose schema ${schema}`, () => {
    const model = normalizeAnalysisReview({ analysisId: "analysis-1", pose: { schema_version: schema, unknown_future_field: true, source: { fps: 25 }, frames: [] }, ergonomics, risk: null, report: null });
    assert.equal(model.poseSchemaVersion, schema);
    assert.equal(model.metrics.trunk_inclination_deg.points[0].value, 12);
    assert.equal(model.metrics.trunk_inclination_deg.points[1].value, null);
    assert.equal(model.metrics.trunk_inclination_deg.statistics.cycleCount, 0);
  });
}

test("normalizer tolerates missing hand activity, holding, risk and report", () => {
  const model = normalizeAnalysisReview({ analysisId: "analysis-2", pose: null, ergonomics: { schema_version: "1.0", frames: [] }, risk: null, report: null });
  assert.equal(model.hands.left.holdingSeconds, null);
  assert.equal(model.risk.level, null);
  assert.deepEqual(model.keyMoments, []);
  assert.equal(model.availableSources.report, false);
});

test("normalizer extracts Holding V2 without inventing object classes", () => {
  const model = normalizeAnalysisReview({
    analysisId: "analysis-3",
    pose: { schema_version: "4.0", summary: { holding: { left: { valid_observation_seconds: 4, likely_holding_seconds: 2, holding_ratio: 0.5, episodes: [{ start_time: 1, end_time: 3, duration_seconds: 2, confidence: 0.8, known_object_class: null }] }, bimanual: { likely_holding_seconds: 0, episode_count: 0 } } }, frames: [] },
    ergonomics: null,
    risk: null,
    report: null,
  });
  assert.equal(model.hands.left.episodes[0].objectClass, null);
  assert.equal(model.hands.left.holdingRatio, 0.5);
});

test("normalizer forwards explicit Pose V6 metric provenance", () => {
  const source = structuredClone(ergonomics);
  source.frames[0].metrics.trunk_inclination_deg.timeline_state = "FLOW_TRACKED";
  source.frames[0].metrics.trunk_inclination_deg.usability = "usable_with_reconstruction";
  const model = normalizeAnalysisReview({ analysisId: "analysis-v6", pose: { schema_version: "6.0", frames: [] }, ergonomics: source, risk: null, report: null });
  const point = model.metrics.trunk_inclination_deg.points[0];
  assert.equal(point.provenance, "FLOW_TRACKED");
  assert.equal(point.usability, "usable_with_reconstruction");
});
