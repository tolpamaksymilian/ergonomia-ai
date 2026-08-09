import assert from "node:assert/strict";
import test from "node:test";

import { formatAngle, formatDuration, formatPercentage, formatTimestamp, UNKNOWN_VALUE } from "../formatters.ts";

test("formatters distinguish zero from missing data", () => {
  assert.equal(formatAngle(0), "0°");
  assert.equal(formatAngle(null), UNKNOWN_VALUE);
  assert.equal(formatDuration(0), "0.0 s");
  assert.equal(formatDuration(undefined), UNKNOWN_VALUE);
});

test("formatters render seconds, minutes, timestamps and percentages", () => {
  assert.equal(formatDuration(72), "1 min 12 s");
  assert.equal(formatTimestamp(64.25), "01:04.3");
  assert.equal(formatTimestamp(59.99), "01:00.0");
  assert.equal(formatPercentage(0.824), "82,4%");
});
