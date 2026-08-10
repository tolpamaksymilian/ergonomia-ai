"use server";

import { revalidatePath } from "next/cache";

import { ejmsMatrixScore, ejmsSectionTwoScore, evaluateMeasurableFactor, evaluateRiskScore, resolveOwasCode, type EjmsLevel } from "@/lib/company-methods/evaluator";
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
    report.report_version = "analysis-report-v2.1-beta.1";
    report.schema_version = "2.1";
    await uploadJson(bucket, analysis.report_path, report);
  }
  revalidatePath(`/panel/analizy/${analysis.id}`);
  revalidatePath(`/panel/analizy/${analysis.id}/raport`);
}

function mergeInputs(previous: JsonRecord, formData: FormData): JsonRecord {
  const riskScore = {
    exposure: optionalText(formData, "risk_exposure"), severity: optionalText(formData, "risk_severity"), probability: optionalText(formData, "risk_probability"),
    activity: optionalText(formData, "risk_activity"), hazard_source: optionalText(formData, "risk_hazard_source"), hazard: optionalText(formData, "risk_hazard"), effect: optionalText(formData, "risk_effect"), controls: optionalText(formData, "risk_controls"),
    psif_sif: optionalText(formData, "risk_psif"), factor_type: optionalText(formData, "risk_factor_type"), work_type: optionalText(formData, "risk_work_type"),
  };
  const sectionTwo: JsonRecord = Object.fromEntries([
    "weight_kg", "horizontal_distance_cm", "start_hand_height_from_waist_cm", "vertical_travel_cm", "frequency_per_minute", "twist_deg", "distance_m",
  ].map((name) => [name, optionalNumber(formData, `ejms_${name}`)]));
  sectionTwo.grip = optionalText(formData, "ejms_grip");
  const oldEjms = record(previous.ejms) ? previous.ejms : {};
  const oldSectionOne = record(oldEjms.section_i) ? oldEjms.section_i : {};
  const sectionOne = Object.fromEntries(EJMS_AREAS.map((area) => [area, {
    ...(record(oldSectionOne[area]) ? oldSectionOne[area] : {}),
    force_level: optionalText(formData, `ejms_force_${area}`),
    frequency_per_minute: optionalNumber(formData, `ejms_frequency_${area}`),
  }]));
  const measurement = optionalNumber(formData, "measurement");
  const limit = optionalNumber(formData, "measurement_limit");
  const measurable = measurement !== null || limit !== null ? [{ measurement, limit, label: optionalText(formData, "measurement_label"), updated_at: optionalText(formData, "measurement_updated_at") }] : [];
  return {
    ...previous,
    schema_version: "1.0", analysis_id: requiredText(formData, "analysis_id"), updated_at: new Date().toISOString(),
    owas: { ...(record(previous.owas) ? previous.owas : {}), load_kg: optionalNumber(formData, "owas_load_kg"), forced_posture: optionalText(formData, "owas_forced_posture") },
    ejms: { ...oldEjms, section_i: sectionOne, section_ii: sectionTwo },
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
    schema_version: "1.0", generated_by: "Ergonomia AI Company Methods Engine", company_methods_version: "company-methods-v1.0-beta.1", analysis_id: analysisId,
  };
  output.generated_at = new Date().toISOString();
  const riskInput = record(inputs.risk_score) ? inputs.risk_score : {};
  output.risk_score = { ...evaluateRiskScore(riskInput), context: riskInput };
  const measurableInputs = Array.isArray(inputs.measurable_factors) ? inputs.measurable_factors.filter(record) : [];
  output.measurable_factors = measurableInputs.map((item) => ({ ...evaluateMeasurableFactor(number(item.measurement), number(item.limit)), label: item.label ?? null, updated_at: item.updated_at ?? null, valid_until: addSixtyMonths(item.updated_at) }));
  const ejms = record(output.ejms) ? output.ejms : {};
  const sectionOneInputs = record(inputs.ejms) && record(inputs.ejms.section_i) ? inputs.ejms.section_i : {};
  if (record(ejms.section_i) && record(ejms.section_i.areas)) {
    const areas = ejms.section_i.areas;
    for (const area of EJMS_AREAS) {
      if (!record(areas[area])) continue;
      const result = areas[area];
      const force = ejmsLevel(record(sectionOneInputs[area]) ? sectionOneInputs[area].force_level : null);
      const posture = ejmsLevel(result.posture_level);
      const manualFrequency = record(sectionOneInputs[area]) ? nullableNumber(sectionOneInputs[area].frequency_per_minute) : null;
      const frequency = manualFrequency === null ? ejmsLevel(result.frequency_duration_level) : classifyEjmsFrequency(area, manualFrequency);
      const postureForce = mergeEjmsPostureForce(posture, force);
      const score = postureForce && frequency ? ejmsMatrixScore(postureForce, frequency) : null;
      const missing = [
        force === null && posture !== "HIGH" ? `ejms.section_i.${area}.force_level` : null,
        frequency === null ? `ejms.section_i.${area}.frequency_or_duration` : null,
      ].filter((item): item is string => item !== null);
      areas[area] = { ...result, force_level: force ?? "UNKNOWN", posture_force_level: postureForce ?? "UNKNOWN", frequency_duration_level: frequency ?? "UNKNOWN", frequency_per_minute: manualFrequency ?? result.frequency_per_minute, frequency_source: manualFrequency === null ? "VIDEO_DERIVED" : "USER_PROVIDED", final_level: score === null ? "UNKNOWN" : postureForce, score, data_status: missing.length ? "PARTIAL" : "COMPLETE", missing_inputs: missing };
    }
    let sectionOneScore = 0;
    for (const item of Object.values(areas)) if (record(item) && typeof item.score === "number") sectionOneScore += item.score;
    ejms.section_i = { ...ejms.section_i, areas, score: sectionOneScore };
  }
  ejms.section_ii = ejmsSectionTwoScore(record(inputs.ejms) && record(inputs.ejms.section_ii) ? inputs.ejms.section_ii : {});
  output.ejms = ejms;
  output.chemical = chemicalResult(record(inputs.chemical) ? inputs.chemical : {});
  const loadKg = record(inputs.owas) ? nullableNumber(inputs.owas.load_kg) : null;
  const forcedPosture = record(inputs.owas) && (inputs.owas.forced_posture === "forced" || inputs.owas.forced_posture === "unforced") ? inputs.owas.forced_posture : null;
  const owas = record(output.owas) ? output.owas : {};
  if (Array.isArray(owas.frames)) {
    owas.frames = owas.frames.map((item) => {
      if (!record(item) || !record(item.components)) return item;
      const components = item.components;
      const prefix = ["back", "arms", "legs"].map((name) => {
        const component = components[name];
        return record(component) ? component.value : null;
      }).join("");
      const resolved = resolveOwasCode(prefix, loadKg);
      return { ...item, ...resolved, components: { ...item.components, load: { value: loadKg === null ? null : loadKg < 10 ? 1 : loadKg <= 20 ? 2 : 3, source: loadKg === null ? "UNKNOWN" : "USER_PROVIDED", known: loadKg !== null } } };
    });
  }
  owas.load_evidence = { value: loadKg, source: loadKg === null ? "UNKNOWN" : "USER_PROVIDED", known: loadKg !== null };
  owas.forced_posture_evidence = { value: forcedPosture, source: forcedPosture === null ? "UNKNOWN" : "USER_PROVIDED", known: forcedPosture !== null };
  if (record(owas.summary) && record(owas.summary.category_ratios)) owas.summary.time_distribution_assessment = owasTimeAssessment(owas.summary.category_ratios, forcedPosture);
  owas.status = loadKg === null || forcedPosture === null ? "PARTIAL" : "AUTOMATIC";
  output.owas = owas;
  const missing = [
    ...(loadKg === null ? ["owas.load_kg"] : []),
    ...(forcedPosture === null ? ["owas.forced_posture"] : []),
    ...(record(output.ejms) && record(output.ejms.section_ii) && Array.isArray(output.ejms.section_ii.missing_inputs) ? output.ejms.section_ii.missing_inputs.filter((item): item is string => typeof item === "string") : []),
    ...(record(output.ejms) && record(output.ejms.section_i) && record(output.ejms.section_i.areas) ? Object.values(output.ejms.section_i.areas).flatMap((area) => record(area) && Array.isArray(area.missing_inputs) ? area.missing_inputs.filter((item): item is string => typeof item === "string") : []) : []),
    ...(record(output.risk_score) && Array.isArray(output.risk_score.missing_inputs) ? output.risk_score.missing_inputs.filter((item): item is string => typeof item === "string").map((item) => `risk_score.${item}`) : []),
  ];
  output.missing_inputs = [...new Set(missing)];
  return output;
}

const EJMS_AREAS = ["neck", "arm", "trunk", "forearm_elbow", "wrist", "fingers_hands", "legs", "static_load"] as const;

function ejmsLevel(value: unknown): EjmsLevel | null { return value === "LOW" || value === "MOD" || value === "HIGH" ? value : null; }
function mergeEjmsPostureForce(posture: EjmsLevel | null, force: EjmsLevel | null): EjmsLevel | null {
  if (posture === "HIGH" || force === "HIGH") return "HIGH";
  if (posture === null) return force;
  if (force === null) return posture === "LOW" ? null : posture;
  const levels: EjmsLevel[] = ["LOW", "MOD", "HIGH"];
  return levels[Math.max(levels.indexOf(posture), levels.indexOf(force))];
}
function classifyEjmsFrequency(area: typeof EJMS_AREAS[number], value: number): EjmsLevel {
  const rules = companyMethodSpecs.ejms.rules.section_i.areas[area];
  const low = "frequency_low_per_minute" in rules && typeof rules.frequency_low_per_minute === "number" ? rules.frequency_low_per_minute : null;
  const high = "frequency_high_per_minute" in rules && typeof rules.frequency_high_per_minute === "number" ? rules.frequency_high_per_minute : null;
  if (high !== null && value > high) return "HIGH";
  if (low !== null && value < low) return "LOW";
  return "MOD";
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

function reportCompanySection(value: JsonRecord): JsonRecord {
  return { status: "available", company_methods_version: value.company_methods_version, missing_inputs: value.missing_inputs, limitations: value.limitations, owas: value.owas, ejms: value.ejms, risk_score: value.risk_score, measurable_factors: value.measurable_factors, chemical: value.chemical };
}

async function parseJson(blob: Blob | null): Promise<JsonRecord> { if (!blob) return {}; try { const value: unknown = JSON.parse(await blob.text()); return record(value) ? value : {}; } catch { return {}; } }
async function uploadJson(bucket: JsonBucket, path: string, value: JsonRecord) { const result = await bucket.upload(path, new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }), { contentType: "application/json", cacheControl: "0", upsert: true }); if (result.error) throw new Error("Nie udało się zapisać prywatnych danych metody."); }
function requiredText(data: FormData, name: string) { const value = optionalText(data, name); if (!value) throw new Error(`Brak pola ${name}.`); return value; }
function optionalText(data: FormData, name: string) { const value = data.get(name); return typeof value === "string" && value.trim() ? value.trim() : null; }
function optionalNumber(data: FormData, name: string) { const value = optionalText(data, name); if (value === null) return null; const parsed = Number(value.replace(",", ".")); if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`Pole ${name} musi być nieujemną liczbą.`); return parsed; }
function optionalSignedNumber(data: FormData, name: string) { const value = optionalText(data, name); if (value === null) return null; const parsed = Number(value.replace(",", ".")); if (!Number.isFinite(parsed)) throw new Error(`Pole ${name} musi być liczbą.`); return parsed; }
function nullableNumber(value: unknown) { return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null; }
function number(value: unknown) { return typeof value === "number" && Number.isFinite(value) ? value : Number.NaN; }
