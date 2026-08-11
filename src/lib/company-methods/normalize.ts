export type CompanyMethodsView = {
  version: string | null;
  owas: Record<string, unknown> | null;
  riskScore: Record<string, unknown> | null;
  measurableFactors: Record<string, unknown>[];
  chemical: Record<string, unknown> | null;
  missingInputs: string[];
};

export function normalizeCompanyMethods(value: unknown): CompanyMethodsView | null {
  if (!record(value) || value.schema_version !== "1.0" || !["company-methods-v1.0-beta.1", "company-methods-v1.1-beta.1", "company-methods-v1.2-beta.1"].includes(String(value.company_methods_version))) return null;
  return {
    version: text(value.company_methods_version),
    owas: record(value.owas) ? value.owas : null,
    riskScore: record(value.risk_score) ? value.risk_score : null,
    measurableFactors: Array.isArray(value.measurable_factors) ? value.measurable_factors.filter(record) : [],
    chemical: record(value.chemical) ? value.chemical : null,
    missingInputs: Array.isArray(value.missing_inputs) ? value.missing_inputs.filter((item): item is string => typeof item === "string") : [],
  };
}

export function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | null { return typeof value === "string" && value.trim() ? value : null; }
