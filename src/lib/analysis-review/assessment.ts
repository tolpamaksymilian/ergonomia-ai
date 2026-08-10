import type {
  AssessmentComponent,
  AssessmentEvidenceSource,
  AssessmentMethodResult,
  AssessmentReview,
  UnknownRecord,
} from "./schemas.ts";
import { isRecord } from "./schemas.ts";

const SOURCES = new Set<AssessmentEvidenceSource>([
  "observed", "derived", "user_provided", "assumed", "unknown",
]);

export function normalizeAssessment(value: unknown): AssessmentReview {
  const root = isRecord(value) && value.schema_version === "1.0" ? value : null;
  const candidates = Array.isArray(root?.candidate_postures)
    ? root.candidate_postures.filter(isRecord)
    : [];
  const keyframes = Array.isArray(root?.keyframes) ? root.keyframes.filter(isRecord) : [];
  return {
    engineVersion: text(root?.engine_version),
    rula: normalizeMethod("RULA", record(root?.rula), candidates, keyframes),
    reba: normalizeMethod("REBA", record(root?.reba), candidates, keyframes),
    candidates: candidates.flatMap((candidate) => {
      const timestamp = number(candidate.timestamp_seconds);
      return timestamp === null ? [] : [{
        id: text(candidate.candidate_id) ?? `assessment-${timestamp}`,
        timestamp,
        quality: number(candidate.quality),
        keyframeUrl: text(keyframes.find((item) => item.candidate_id === candidate.candidate_id)?.signed_url),
      }];
    }),
    limitations: strings(root?.limitations),
  };
}

function normalizeMethod(
  method: "RULA" | "REBA",
  summary: UnknownRecord | null,
  candidates: UnknownRecord[],
  keyframes: UnknownRecord[],
): AssessmentMethodResult {
  const representative = record(summary?.representative);
  const side = representative?.side === "left" || representative?.side === "right"
    ? representative.side
    : null;
  const candidateId = text(representative?.candidate_id);
  const candidate = candidateId
    ? candidates.find((item) => item.candidate_id === candidateId) ?? null
    : null;
  const rawMethod = candidate && side ? record(record(candidate[method.toLowerCase()])?.[side]) : null;
  const range = record(representative?.score_range) ?? record(rawMethod?.score_range);
  return {
    method,
    status: status(summary?.status),
    applicability: applicability(summary?.applicability),
    side,
    finalScore: number(representative?.final_score),
    scoreRange: range && number(range.min) !== null && number(range.max) !== null
      ? { min: number(range.min)!, max: number(range.max)! }
      : null,
    coverage: number(rawMethod?.evidence_coverage_ratio),
    quality: number(representative?.quality) ?? number(rawMethod?.data_quality),
    timestamp: number(representative?.timestamp_seconds),
    candidateId,
    keyframeUrl: text(keyframes.find((item) => item.candidate_id === candidateId)?.signed_url)
      ?? text(candidate?.keyframe_url),
    missingInputs: strings(representative?.missing_inputs ?? rawMethod?.missing_inputs),
    components: normalizeComponents(rawMethod?.components),
  };
}

function normalizeComponents(value: unknown): AssessmentComponent[] {
  if (!isRecord(value)) return [];
  return Object.entries(value).flatMap(([name, raw]) => {
    if (!isRecord(raw)) return [];
    const source = SOURCES.has(raw.source as AssessmentEvidenceSource)
      ? raw.source as AssessmentEvidenceSource
      : "unknown";
    return [{ name, rawInput: primitive(raw.raw_input), category: text(raw.derived_category),
      score: number(raw.score_component), quality: number(raw.quality), source,
      evidence: strings(raw.evidence), missingEvidence: strings(raw.missing_evidence), notes: strings(raw.notes) }];
  });
}

function status(value: unknown): AssessmentMethodResult["status"] {
  return value === "COMPLETE" || value === "PARTIAL" ? value : "INSUFFICIENT_DATA";
}
function applicability(value: unknown): AssessmentMethodResult["applicability"] {
  return value === "GOOD" || value === "LIMITED" ? value : "INSUFFICIENT";
}
function record(value: unknown): UnknownRecord | null { return isRecord(value) ? value : null; }
function text(value: unknown): string | null { return typeof value === "string" && value.trim() ? value.trim() : null; }
function number(value: unknown): number | null { return typeof value === "number" && Number.isFinite(value) ? value : null; }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []; }
function primitive(value: unknown): number | string | boolean | null { return typeof value === "number" || typeof value === "string" || typeof value === "boolean" ? value : null; }
