import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ejmsMatrixScore, ejmsSectionTwoScore, evaluateMeasurableFactor, evaluateRiskScore, resolveOwasCode } from "../evaluator.ts";

const golden = JSON.parse(readFileSync(new URL("../../../../worker/tests/fixtures/company-methods-golden.json", import.meta.url), "utf8"));

test("measurable boundaries match workbook", () => {
  assert.equal(evaluateMeasurableFactor(49.99, 100).level, "small");
  assert.equal(evaluateMeasurableFactor(50, 100).level, "medium");
  assert.equal(evaluateMeasurableFactor(100, 100).level, "medium");
  assert.equal(evaluateMeasurableFactor(100.01, 100).level, "large");
});

test("Risk Score is explicitly normalized", () => {
  const result = evaluateRiskScore({ exposure: "constant", severity: "serious_injury", probability: "very_likely" });
  assert.equal(result.value, 700);
  assert.equal(result.category, "Bardzo wysokie ryzyko");
  assert.equal(result.formula_status, "NORMALIZED_INTERPRETATION");
});

test("all EJMS matrix combinations match workbook", () => {
  assert.deepEqual([["LOW", "LOW"], ["LOW", "MOD"], ["LOW", "HIGH"], ["MOD", "LOW"], ["MOD", "MOD"], ["MOD", "HIGH"], ["HIGH", "LOW"], ["HIGH", "MOD"], ["HIGH", "HIGH"]].map(([a, b]) => ejmsMatrixScore(a, b)), [0, 5, 10, 5, 10, 15, 10, 15, 20]);
});

test("EJMS section II preserves unknown absolute values", () => {
  const result = ejmsSectionTwoScore({ frequency_per_minute: 2, twist_deg: 20 });
  assert.equal(result.components.frequency_per_minute.score, 10);
  assert.equal(result.components.twist_deg.score, 5);
  assert.equal(result.components.weight_kg.score, null);
});

test("OWAS 3133 remains source ambiguous", () => {
  const result = resolveOwasCode("313", 25);
  assert.equal(result.status, "SOURCE_ERROR");
  assert.deepEqual(result.possible_categories[0].categories, [2, 3]);
});

test("unknown OWAS load produces three possibilities", () => {
  assert.equal(resolveOwasCode("112", null).possible_categories.length, 3);
});

test("TypeScript matches shared Python golden fixture", () => {
  const risk = evaluateRiskScore(golden.risk_score.input);
  assert.equal(risk.value, golden.risk_score.expected.value);
  assert.equal(risk.category, golden.risk_score.expected.category);
  for (const item of golden.measurable) assert.equal(evaluateMeasurableFactor(item.measurement, item.limit).level, item.level);
  for (const item of golden.ejms_matrix) assert.equal(ejmsMatrixScore(item.posture, item.frequency), item.score);
  const owas = resolveOwasCode(golden.owas.prefix, golden.owas.load_kg);
  assert.equal(owas.code, golden.owas.expected_code);
  assert.equal(owas.category, golden.owas.expected_category);
});
