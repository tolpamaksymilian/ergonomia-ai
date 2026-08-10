import assert from "node:assert/strict";
import test from "node:test";

import { parseAnalysisReport, parseReportSummary } from "../../analysis-report.ts";

const base = {
  generated_by: "Ergonomia AI Report Engine",
  generated_at: "2026-08-10T00:00:00Z",
  analysis: { analysis_id: "a", title: "A", analyzed_frames: 1 },
  processing: {},
  data_quality: {},
  risk_summary: { overall_level: "low" },
  body_areas: [], metric_summary: [], key_moments: [], observations: [], limitations: [], disclaimer: "x",
};

test("parser keeps Report V1 compatibility", () => {
  assert.ok(parseAnalysisReport({ ...base, schema_version: "1.0", report_version: "analysis-report-v1.0" }));
});

test("parser accepts Report V2", () => {
  assert.ok(parseAnalysisReport({ ...base, schema_version: "2.0", report_version: "analysis-report-v2.0-beta.1", executive_summary: [] }));
});

test("summary parser accepts both report versions", () => {
  const summary = { analysis_id: "a", overall_level: "low", insufficient_data: false, valid_metric_ratio: 1, key_moments_count: 0, metric_count: 14, profile_status: "development" };
  assert.ok(parseReportSummary({ ...summary, report_version: "analysis-report-v1.0" }));
  assert.ok(parseReportSummary({ ...summary, report_version: "analysis-report-v2.0-beta.1" }));
});
