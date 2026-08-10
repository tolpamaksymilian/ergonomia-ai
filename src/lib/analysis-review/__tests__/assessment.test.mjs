import assert from "node:assert/strict";
import test from "node:test";

import { normalizeAssessment } from "../assessment.ts";

function document(status = "PARTIAL") {
  const method = {
    status,
    applicability: status === "INSUFFICIENT_DATA" ? "INSUFFICIENT" : "LIMITED",
    representative: status === "INSUFFICIENT_DATA" ? null : {
      candidate_id: "posture-1", side: "right", timestamp_seconds: 2.5,
      quality: 0.8, final_score: status === "COMPLETE" ? 4 : null,
      score_range: status === "COMPLETE" ? { min: 4, max: 4 } : { min: 3, max: 6 },
      missing_inputs: status === "COMPLETE" ? [] : ["external_load"],
    },
  };
  return {
    schema_version: "1.0", engine_version: "assessment-v1.0-beta.1",
    rula: method, reba: method, limitations: ["analysis_based_on_2d_video"],
    candidate_postures: [{
      candidate_id: "posture-1", timestamp_seconds: 2.5, quality: 0.8,
      rula: { right: { evidence_coverage_ratio: 0.7, data_quality: 0.8, score_range: method.representative?.score_range,
        components: { force_load: { raw_input: null, derived_category: null, score_component: null, quality: 0, source: "unknown", evidence: [], missing_evidence: ["external_load"], notes: [] } } } },
      reba: { right: { evidence_coverage_ratio: 0.6, data_quality: 0.8, score_range: method.representative?.score_range, components: {} } },
    }],
  };
}

test("normalizes partial range and missing evidence", () => {
  const result = normalizeAssessment(document());
  assert.equal(result.rula.status, "PARTIAL");
  assert.deepEqual(result.rula.scoreRange, { min: 3, max: 6 });
  assert.equal(result.rula.finalScore, null);
  assert.equal(result.rula.components[0].source, "unknown");
});

test("normalizes complete score without changing it", () => {
  const result = normalizeAssessment(document("COMPLETE"));
  assert.equal(result.rula.status, "COMPLETE");
  assert.equal(result.rula.finalScore, 4);
  assert.deepEqual(result.rula.scoreRange, { min: 4, max: 4 });
});

test("normalizes insufficient data without zero", () => {
  const result = normalizeAssessment(document("INSUFFICIENT_DATA"));
  assert.equal(result.rula.status, "INSUFFICIENT_DATA");
  assert.equal(result.rula.finalScore, null);
  assert.equal(result.rula.scoreRange, null);
});

test("old analyses remain available with empty assessment", () => {
  const result = normalizeAssessment(null);
  assert.equal(result.engineVersion, null);
  assert.equal(result.rula.status, "INSUFFICIENT_DATA");
  assert.equal(result.candidates.length, 0);
});
