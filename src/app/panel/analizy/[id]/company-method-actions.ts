"use server";

import { revalidatePath } from "next/cache";

import { evaluateMeasurableFactor, evaluateRiskScore, resolveOwasCode } from "@/lib/company-methods/evaluator";
import { record } from "@/lib/company-methods/normalize";
import { companyMethodSpecs } from "@/lib/company-methods/specs";
import { requireUser } from "@/lib/auth/access";

type JsonRecord = Record<string, unknown>;
type JsonBucket = {
  upload(path: string, body: Blob, options: { contentType: string; cacheControl: string; upsert: boolean }): Promise<{ error: unknown }>;
};

export async function saveCompanyMethodInputs(formData: FormData): Promise<void> {
  const analysisId = requiredText(formData, "analysis_id");
  const { supabase } = await requireUser();
  const { data: analysis, error } = await supabase.from("analyses").select("id,user_id,report_path").eq("id", analysisId).maybeSingle();
  if (error) throw new Error("Nie udało się zweryfikować dostępu do analizy.");
  if (!analysis) throw new Error("Analiza nie istnieje albo nie masz do niej dostępu.");

  const base = `${analysis.user_id}/${analysis.id}/results`;
  const bucket = supabase.storage.from("analysis-results");
  const inputsPath = `${base}/company-method-inputs.json`;
  const assessmentPath = `${base}/company-method-assessment.json`;
  const [oldInputsFile, assessmentFile, reportFile] = await Promise.all([
    bucket.download(inputsPath),
    bucket.download(assessmentPath),
    analysis.report_path ? bucket.download(analysis.report_path) : Promise.resolve({ data: null, error: null }),
  ]);
  const oldInputs = await parseJson(oldInputsFile.data);
  const assessment = await parseJson(assessmentFile.data);
  const report = await parseJson(reportFile.data);
  const inputs = mergeInputs(oldInputs, formData);
  const updatedAssessment = recalculateAssessment(assessment, inputs, analysis.id);

  await uploadJson(bucket, inputsPath, inputs);
  await uploadJson(bucket, assessmentPath, updatedAssessment);
  if (analysis.report_path && record(report)) {
    report.company_methods = reportCompanySection(updatedAssessment);
    report.report_version = "analysis-report-v2.3-beta.1";
    report.schema_version = "2.3";
    await uploadJson(bucket, analysis.report_path, report);
  }
  revalidatePath(`/panel/analizy/${analysis.id}`);
  revalidatePath(`/panel/analizy/${analysis.id}/raport`);
}

function mergeInputs(previous: JsonRecord, formData: FormData): JsonRecord {
  const sharedLoadKg = optionalNumber(formData, "handled_load_kg");
  const riskScore = {
    exposure: optionalText(formData, "risk_exposure"), severity: optionalText(formData, "risk_severity"), probability: optionalText(formData, "risk_probability"),
    activity: optionalText(formData, "risk_activity"), hazard_source: optionalText(formData, "risk_hazard_source"), hazard: optionalText(formData, "risk_hazard"), effect: optionalText(formData, "risk_effect"), controls: optionalText(formData, "risk_controls"),
    psif_sif: optionalText(formData, "risk_psif"), factor_type: optionalText(formData, "risk_factor_type"), work_type: optionalText(formData, "risk_work_type"),
  };
  const measurement = optionalNumber(formData, "measurement");
  const limit = optionalNumber(formData, "measurement_limit");
  const measurable = measurement !== null || limit !== null ? [{ measurement, limit, label: optionalText(formData, "measurement_label"), updated_at: optionalText(formData, "measurement_updated_at") }] : [];
  return {
    ...previous,
    schema_version: "1.0", analysis_id: requiredText(formData, "analysis_id"), updated_at: new Date().toISOString(),
    owas: { ...(record(previous.owas) ? previous.owas : {}), load_kg: sharedLoadKg, forced_posture: optionalText(formData, "owas_forced_posture") },
    risk_score: riskScore,
    measurable_factors: measurable,
    chemical: {
      substance_name: optionalText(formData, "chemical_name"), manufacturer: optionalText(formData, "chemical_manufacturer"),
      h_statements: optionalText(formData, "chemical_h_statements"), classified_safe: formData.get("chemical_safe") === "on",
      hazard_level: optionalText(formData, "chemical_hazard_level"), boiling_point_c: optionalSignedNumber(formData, "chemical_boiling_point_c"),
      working_temperature_c: optionalSignedNumber(formData, "chemical_working_temperature_c"), volatility: optionalText(formData, "chemical_volatility"),
      solid_category: optionalText(formData, "chemical_solid_category"), exposure_time: optionalText(formData, "chemical_exposure_time"), quantity: optionalText(formData, "chemical_quantity"),
      risk_level: optionalText(formData, "chemical_risk_level"), residual_risk_level: optionalText(formData, "chemical_residual_risk_level"),
    },
  };
}

function recalculateAssessment(current: JsonRecord, inputs: JsonRecord, analysisId: string): JsonRecord {
  const output: JsonRecord = record(current) ? structuredClone(current) : {
    schema_version: "1.0", generated_by: "Ergonomia AI Company Methods Engine", company_methods_version: "company-methods-v1.2-beta.1", analysis_id: analysisId,
  };
  output.generated_at = new Date().toISOString();
  const riskInput = record(inputs.risk_score) ? inputs.risk_score : {};
  output.risk_score = { ...evaluateRiskScore(riskInput), context: riskInput };
  const measurableInputs = Array.isArray(inputs.measurable_factors) ? inputs.measurable_factors.filter(record) : [];
  output.measurable_factors = measurableInputs.map((item) => ({ ...evaluateMeasurableFactor(number(item.measurement), number(item.limit)), label: item.label ?? null, updated_at: item.updated_at ?? null, valid_until: addSixtyMonths(item.updated_at) }));
  output.chemical = chemicalResult(record(inputs.chemical) ? inputs.chemical : {});
  const loadKg = record(inputs.owas) ? nullableNumber(inputs.owas.load_kg) : null;
  const forcedPosture = record(inputs.owas) && (inputs.owas.forced_posture === "forced" || inputs.owas.forced_posture === "unforced") ? inputs.owas.forced_posture : null;
  const owas = record(output.owas) ? output.owas : {};
  if (Array.isArray(owas.frames)) {
    const recalculatedFrames = owas.frames.map((item) => {
      if (!record(item) || !record(item.components)) return item;
      const components = item.components;
      const prefix = ["back", "arms", "legs"].map((name) => {
        const component = components[name];
        return record(component) ? component.value : null;
      }).join("");
      const resolved = resolveOwasCode(prefix, loadKg);
      return { ...item, ...resolved, components: { ...item.components, load: { value: loadKg === null ? null : loadKg < 10 ? 1 : loadKg <= 20 ? 2 : 3, source: loadKg === null ? "UNKNOWN" : "USER_PROVIDED", known: loadKg !== null } } };
    });
    owas.frames = recalculatedFrames;
    owas.summary = rebuildOwasSummary(recalculatedFrames, record(owas.summary) ? owas.summary : {});
  }
  owas.load_evidence = { value: loadKg, source: loadKg === null ? "UNKNOWN" : "USER_PROVIDED", known: loadKg !== null };
  owas.forced_posture_evidence = { value: forcedPosture, source: forcedPosture === null ? "UNKNOWN" : "USER_PROVIDED", known: forcedPosture !== null };
  if (record(owas.summary) && record(owas.summary.category_ratios)) owas.summary.time_distribution_assessment = owasTimeAssessment(owas.summary.category_ratios, forcedPosture);
  owas.status = loadKg === null || forcedPosture === null ? "PARTIAL" : "AUTOMATIC";
  output.owas = owas;
  const missing = [
    ...(loadKg === null ? ["owas.load_kg"] : []),
    ...(forcedPosture === null ? ["owas.forced_posture"] : []),
    ...(record(output.risk_score) && Array.isArray(output.risk_score.missing_inputs) ? output.risk_score.missing_inputs.filter((item): item is string => typeof item === "string").map((item) => `risk_score.${item}`) : []),
  ];
  output.missing_inputs = [...new Set(missing)];
  return output;
}

function addSixtyMonths(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const targetYear = year + 5;
  const lastDay = new Date(Date.UTC(targetYear, month, 0)).getUTCDate();
  return `${targetYear.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${Math.min(day, lastDay).toString().padStart(2, "0")}`;
}
function owasTimeAssessment(ratios: JsonRecord, posture: "forced" | "unforced" | null): JsonRecord[] {
  return [1, 2, 3, 4].map((category) => {
    const storedRatio = ratios[String(category)];
    const ratio = typeof storedRatio === "number" ? storedRatio : 0;
    const matches = companyMethodSpecs.owas.thresholds.time_distribution.filter((rawRule) => {
      const rule: JsonRecord = record(rawRule) ? rawRule as JsonRecord : {};
      if (!Array.isArray(rule.categories) || !rule.categories.includes(category)) return false;
      const byCategory: JsonRecord = record(rule.posture_by_category) ? rule.posture_by_category as JsonRecord : {};
      const expected = typeof byCategory[String(category)] === "string" ? byCategory[String(category)] : rule.posture;
      const minimum = typeof rule.minimum_ratio === "number" ? rule.minimum_ratio : null;
      const minimumExclusive = typeof rule.minimum_ratio_exclusive === "number" ? rule.minimum_ratio_exclusive : null;
      const maximum = typeof rule.maximum_ratio === "number" ? rule.maximum_ratio : null;
      return posture !== null && expected === posture && (minimum === null || ratio >= minimum) && (minimumExclusive === null || ratio > minimumExclusive) && (maximum === null || ratio <= maximum);
    });
    const levels = [...new Set(matches.map((rule) => record(rule) ? rule.level : null).filter((level): level is string => typeof level === "string"))];
    return { category, ratio, posture: posture ?? "UNKNOWN", level: levels.length === 1 ? levels[0] : null, status: levels.length === 1 ? "VERIFIED" : levels.length > 1 ? "SOURCE_AMBIGUOUS" : "REQUIRES_DATA", matching_rules: matches.map((rule) => ({ level: rule.level, source_ref: `OWAS!${rule.source_ref}` })) };
  });
}

function chemicalResult(input: JsonRecord): JsonRecord {
  const safe = input.classified_safe === true;
  const hasData = Object.values(input).some((value) => value !== null && value !== "" && value !== false);
  return { method_id: "chemical-inhalation-company", status: !hasData ? "REQUIRES_DATA" : safe ? "MANUAL" : "PARTIAL", automatic_scoring_enabled: false, classified_safe: safe, inputs: input, risk_level: input.risk_level ?? null, residual_risk_level: input.residual_risk_level ?? null, missing_inputs: safe ? [] : ["IN.06.13"], limitation: "IN.06.13_NOT_INCLUDED" };
}

function rebuildOwasSummary(frames: unknown[], previous: JsonRecord): JsonRecord {
  const durations = new Map<number, number>();
  const postureDurations = new Map<string, number>();
  let total = 0;
  for (const raw of frames) {
    if (!record(raw)) continue;
    const duration = typeof raw.duration_seconds === "number" ? raw.duration_seconds : 0;
    total += duration;
    if (typeof raw.posture_code === "string") postureDurations.set(raw.posture_code, (postureDurations.get(raw.posture_code) ?? 0) + duration);
    if (typeof raw.category === "number") durations.set(raw.category, (durations.get(raw.category) ?? 0) + duration);
  }
  const classified = [...durations.values()].reduce((sum, value) => sum + value, 0);
  const postureClassified = [...postureDurations.values()].reduce((sum, value) => sum + value, 0);
  const categoryDuration = Object.fromEntries([1, 2, 3, 4].map((category) => [String(category), Number((durations.get(category) ?? 0).toFixed(6))]));
  return {
    ...previous,
    classified_duration_seconds: Number(classified.toFixed(6)),
    posture_classified_duration_seconds: Number(postureClassified.toFixed(6)),
    active_duration_seconds: Number(total.toFixed(6)),
    category_duration_seconds: categoryDuration,
    category_ratios: Object.fromEntries(Object.entries(categoryDuration).map(([key, value]) => [key, total > 0 ? Number((value / total).toFixed(6)) : 0])),
    posture_duration_seconds: Object.fromEntries([...postureDurations].map(([key, value]) => [key, Number(value.toFixed(6))])),
    posture_coverage_ratio: total > 0 ? Number((postureClassified / total).toFixed(6)) : 0,
    dominant_category: [...durations.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? null,
  };
}

function reportCompanySection(value: JsonRecord): JsonRecord {
  return { status: "available", company_methods_version: value.company_methods_version, missing_inputs: value.missing_inputs, limitations: value.limitations, owas: value.owas, risk_score: value.risk_score, measurable_factors: value.measurable_factors, chemical: value.chemical };
}

async function parseJson(blob: Blob | null): Promise<JsonRecord> { if (!blob) return {}; try { const value: unknown = JSON.parse(await blob.text()); return record(value) ? value : {}; } catch { return {}; } }
async function uploadJson(bucket: JsonBucket, path: string, value: JsonRecord) { const result = await bucket.upload(path, new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }), { contentType: "application/json", cacheControl: "0", upsert: true }); if (result.error) throw new Error("Nie udało się zapisać prywatnych danych metody."); }
function requiredText(data: FormData, name: string) { const value = optionalText(data, name); if (!value) throw new Error(`Brak pola ${name}.`); return value; }
function optionalText(data: FormData, name: string) { const value = data.get(name); return typeof value === "string" && value.trim() ? value.trim() : null; }
function optionalNumber(data: FormData, name: string) { const value = optionalText(data, name); if (value === null) return null; const parsed = Number(value.replace(",", ".")); if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`Pole ${name} musi być nieujemną liczbą.`); return parsed; }
function optionalSignedNumber(data: FormData, name: string) { const value = optionalText(data, name); if (value === null) return null; const parsed = Number(value.replace(",", ".")); if (!Number.isFinite(parsed)) throw new Error(`Pole ${name} musi być liczbą.`); return parsed; }
function nullableNumber(value: unknown) { return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null; }
function number(value: unknown) { return typeof value === "number" && Number.isFinite(value) ? value : Number.NaN; }
