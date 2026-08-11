import assert from "node:assert/strict";
import test from "node:test";

import { calculateAnalysisCompleteness, normalizeAnalysisContext } from "../../../types/analysis-context.ts";
import { normalizeCompanyMethods } from "../../company-methods/normalize.ts";

test("manual analysis context is normalized and bounded", () => {
  const context = normalizeAnalysisContext({ process_name: "  Pakowanie  ", notes: 42 });
  assert.equal(context.process_name, "Pakowanie");
  assert.equal(context.notes, null);
  assert.equal(context.schema_version, "1.0");
});

test("completeness describes form coverage, not AI accuracy", () => {
  const context = normalizeAnalysisContext({ process_name: "Montaż", department: "Produkcja" });
  const result = calculateAnalysisCompleteness({ workstation: null, context });
  assert.equal(result.total, 6);
  assert.equal(result.completed, 2);
  assert.equal(result.percentage, 33);
});

test("legacy company methods payload accepts but ignores EJMS", () => {
  const result = normalizeCompanyMethods({ schema_version: "1.0", company_methods_version: "company-methods-v1.1-beta.1", owas: {}, ejms: { score: 99 } });
  assert.ok(result);
  assert.equal("ejms" in result, false);
});
