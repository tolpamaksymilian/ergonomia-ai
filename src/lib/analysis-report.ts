import type {
  AnalysisReport,
  ReportSummary,
  RiskLevel,
  RiskProfileStatus,
} from "@/types/analysis";

const riskLevels = new Set<RiskLevel>([
  "low",
  "moderate",
  "high",
  "critical",
  "insufficient_data",
]);

const profileStatuses = new Set<RiskProfileStatus>([
  "development",
  "draft",
  "approved",
  "archived",
]);

export function parseAnalysisReport(value: unknown): AnalysisReport | null {
  if (!isRecord(value)) return null;
  if (
    value.schema_version !== "1.0" ||
    value.report_version !== "analysis-report-v1.0" ||
    value.generated_by !== "Ergonomia AI Report Engine" ||
    typeof value.generated_at !== "string" ||
    !isRecord(value.analysis) ||
    typeof value.analysis.analysis_id !== "string" ||
    typeof value.analysis.title !== "string" ||
    typeof value.analysis.analyzed_frames !== "number" ||
    !isRecord(value.processing) ||
    !isRecord(value.data_quality) ||
    !isRecord(value.risk_summary) ||
    !isRiskLevel(value.risk_summary.overall_level) ||
    !Array.isArray(value.body_areas) ||
    !Array.isArray(value.metric_summary) ||
    !Array.isArray(value.key_moments) ||
    !Array.isArray(value.observations) ||
    !Array.isArray(value.limitations) ||
    typeof value.disclaimer !== "string"
  ) {
    return null;
  }
  return value as AnalysisReport;
}

export function parseReportSummary(value: unknown): ReportSummary | null {
  if (
    !isRecord(value) ||
    value.report_version !== "analysis-report-v1.0" ||
    typeof value.analysis_id !== "string" ||
    !isRiskLevel(value.overall_level) ||
    typeof value.insufficient_data !== "boolean" ||
    typeof value.valid_metric_ratio !== "number" ||
    typeof value.key_moments_count !== "number" ||
    typeof value.metric_count !== "number" ||
    !isProfileStatus(value.profile_status)
  ) {
    return null;
  }
  return value as ReportSummary;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRiskLevel(value: unknown): value is RiskLevel {
  return typeof value === "string" && riskLevels.has(value as RiskLevel);
}

function isProfileStatus(value: unknown): value is RiskProfileStatus {
  return (
    typeof value === "string" &&
    profileStatuses.has(value as RiskProfileStatus)
  );
}
