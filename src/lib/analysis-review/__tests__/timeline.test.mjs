import assert from "node:assert/strict";
import test from "node:test";

import { downsampleMetricPoints, mergeTimelineSegments } from "../timeline.ts";

test("timeline sorts and merges adjacent equivalent episodes", () => {
  const result = mergeTimelineSegments([
    { layer: "holding", track: "left", label: "Chwyt", start: 1.1, end: 2 },
    { layer: "holding", track: "left", label: "Chwyt", start: 0, end: 1 },
    { layer: "holding", track: "right", label: "Chwyt", start: 0.5, end: 1.5 },
  ], 0.11);
  assert.equal(result.length, 2);
  assert.deepEqual([result[0].start, result[0].end], [0, 2]);
  assert.equal(result[1].track, "right");
});

test("timeline rejects invalid timestamps", () => {
  const result = mergeTimelineSegments([
    { layer: "quality", track: "body", label: "Low", start: Number.NaN, end: 1 },
    { layer: "quality", track: "body", label: "Low", start: 2, end: 1 },
  ]);
  assert.deepEqual(result, []);
});

test("timeline preserves provenance boundaries", () => {
  const result = mergeTimelineSegments([
    { layer: "posture", track: "left_wrist", label: "Nadgarstek", start: 0, end: 0.1, band: "unknown", provenance: "TEMPORALLY_RECONSTRUCTED", usability: "usable_for_timeline_only" },
    { layer: "posture", track: "left_wrist", label: "Nadgarstek", start: 0.1, end: 0.2, band: "unknown", provenance: "NO_DATA", usability: "insufficient" },
  ]);
  assert.equal(result.length, 2);
  assert.equal(result[0].provenance, "TEMPORALLY_RECONSTRUCTED");
});

test("downsampling preserves extrema and invalid gaps", () => {
  const points = Array.from({ length: 2000 }, (_, index) => ({
    time: index / 10,
    value: index === 777 ? 999 : index === 1000 ? null : Math.sin(index / 20),
    quality: 0.9,
    valid: index !== 1000,
    band: index === 1000 ? "unknown" : "neutral",
    sourceFrameIndex: index,
    outputFrameIndex: index,
    provenance: null,
    usability: null,
  }));
  const result = downsampleMetricPoints(points, 200);
  assert.ok(result.length <= 200);
  assert.ok(result.some((point) => point.value === 999));
  assert.ok(result.some((point) => point.valid === false));
});
