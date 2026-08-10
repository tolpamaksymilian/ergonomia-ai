import { companyMethodSpecs } from "./specs.ts";

export type EvidenceSource = "VIDEO_DERIVED" | "USER_PROVIDED" | "MEASUREMENT" | "WORKBOOK_RULE" | "UNKNOWN";
export type EjmsLevel = "LOW" | "MOD" | "HIGH";

type UnknownRecord = Record<string, unknown>;

export function evaluateRiskScore(input: UnknownRecord) {
  const thresholds = companyMethodSpecs.riskScore.thresholds;
  const exposure = thresholds.exposure.find((item) => item.id === input.exposure);
  const severity = thresholds.severity.find((item) => item.id === input.severity);
  const probability = thresholds.probability.find((item) => item.id === input.probability);
  const missingInputs = [!exposure && "exposure", !severity && "severity", !probability && "probability"].filter((item): item is string => Boolean(item));
  const context = Object.fromEntries(["activity", "hazard_source", "hazard", "effect", "controls", "psif_sif", "factor_type", "work_type"].map((name) => [name, input[name] ?? null]));
  if (!exposure || !severity || !probability) {
    return { method_id: "company-risk-score", status: "REQUIRES_DATA", formula_status: "NORMALIZED_INTERPRETATION", value: null, category: null, action: null, acceptability: null, context, missing_inputs: missingInputs, trace: ["SOURCE_FORMULA_MISSING"] } as const;
  }
  const value = exposure.value * severity.value * probability.value;
  const band = thresholds.risk_bands.find((item) => {
    const minimum = "minimum_exclusive" in item ? item.minimum_exclusive : null;
    return (item.maximum === null || value <= item.maximum) && (minimum === null || minimum === undefined || value > minimum);
  });
  if (!band) throw new Error("Risk Score value does not match a source band.");
  return { method_id: "company-risk-score", status: "MANUAL", formula_status: "NORMALIZED_INTERPRETATION", value, category: band.category, action: band.action, acceptability: band.acceptability, context, missing_inputs: [], trace: ["form_ Risk_Score!J5:AH8", "form_ Risk_Score!AJ6:AL20", "SOURCE_FORMULA_MISSING"] } as const;
}

export function evaluateMeasurableFactor(measurement: number, limit: number) {
  if (!Number.isFinite(measurement) || !Number.isFinite(limit) || measurement < 0 || limit <= 0) {
    return { status: "REQUIRES_DATA", level: null, label: null, acceptability: null, ratio: null } as const;
  }
  const ratio = measurement / limit;
  if (measurement > limit) return { status: "MANUAL", level: "large", label: "Duże", acceptability: "Niedopuszczalne", ratio } as const;
  if (measurement >= 0.5 * limit) return { status: "MANUAL", level: "medium", label: "Średnie", acceptability: "Dopuszczalne", ratio } as const;
  return { status: "MANUAL", level: "small", label: "Małe", acceptability: "Dopuszczalne", ratio } as const;
}

export function ejmsMatrixScore(posture: EjmsLevel, frequency: EjmsLevel): number {
  return companyMethodSpecs.ejms.rules.matrix[posture][frequency];
}

export function ejmsSectionTwoScore(input: UnknownRecord) {
  const thresholds = companyMethodSpecs.ejms.thresholds.section_ii;
  const numericFields = ["weight_kg", "horizontal_distance_cm", "start_hand_height_from_waist_cm", "vertical_travel_cm", "frequency_per_minute", "twist_deg", "distance_m"] as const;
  const components: Record<string, { value: unknown; score: number | null; source: EvidenceSource }> = {};
  for (const field of numericFields) {
    const value = finite(input[field]);
    components[field] = { value, score: bandScore(value, thresholds[field]), source: value === null ? "UNKNOWN" : "USER_PROVIDED" };
  }
  const grip = typeof input.grip === "string" && input.grip in thresholds.grip ? input.grip as keyof typeof thresholds.grip : null;
  components.grip = { value: grip, score: grip ? thresholds.grip[grip] : null, source: grip ? "USER_PROVIDED" : "UNKNOWN" };
  const missing_inputs = Object.entries(components).filter(([, item]) => item.score === null).map(([name]) => `ejms.section_ii.${name}`);
  return { status: missing_inputs.length ? "PARTIAL" : "MANUAL", score: Object.values(components).reduce((sum, item) => sum + (item.score ?? 0), 0), components, missing_inputs } as const;
}

export function resolveOwasCode(codePrefix: string, loadKg: number | null) {
  if (!/^[1-4][1-3][1-7]$/.test(codePrefix)) return { status: "REQUIRES_DATA", code: null, category: null, possible_categories: [] };
  const loads = loadKg === null || !Number.isFinite(loadKg) || loadKg < 0 ? [1, 2, 3] : [loadKg < 10 ? 1 : loadKg <= 20 ? 2 : 3];
  const possible = loads.map((load) => {
    const code = `${codePrefix}${load}`;
    const item = companyMethodSpecs.owas.lookup[code as keyof typeof companyMethodSpecs.owas.lookup];
    return { code, status: item?.status ?? "SOURCE_MISSING", categories: item?.categories ?? [] };
  });
  const exact = possible.length === 1 && possible[0].status === "VERIFIED" && possible[0].categories.length === 1 ? possible[0] : null;
  return { status: exact ? "MANUAL" : possible.some((item) => item.status === "SOURCE_AMBIGUOUS") ? "SOURCE_ERROR" : "PARTIAL", code: exact?.code ?? null, category: exact?.categories[0] ?? null, possible_categories: possible };
}

function bandScore(value: number | null, bands: ReadonlyArray<ReadonlyArray<number | null>>): number | null {
  if (value === null) return null;
  const match = bands.find(([minimum, maximum]) => (minimum === null || value >= minimum) && (maximum === null || value <= maximum));
  const score = match?.[2];
  return typeof score === "number" ? score : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
