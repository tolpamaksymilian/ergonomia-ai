import test from "node:test";
import assert from "node:assert/strict";

import {
  accountStatusLabel,
  companyRoleLabel,
  isDashboardPathActive,
  relationName,
} from "../presentation.ts";

test("sidebar active state respects exact dashboard links", () => {
  assert.equal(isDashboardPathActive("/panel", "/panel", true), true);
  assert.equal(isDashboardPathActive("/panel/analizy", "/panel", true), false);
  assert.equal(isDashboardPathActive("/panel/analizy/123", "/panel/analizy"), true);
});

test("role and account labels are stable", () => {
  assert.equal(companyRoleLabel("admin"), "Administrator firmy");
  assert.equal(companyRoleLabel("reviewer"), "Reviewer");
  assert.equal(companyRoleLabel(null), "Użytkownik");
  assert.equal(accountStatusLabel("pending"), "Oczekujące");
  assert.equal(accountStatusLabel("inactive"), "Nieaktywne");
  assert.equal(accountStatusLabel(null), "Aktywne");
});

test("relation helper supports Supabase object and array shapes", () => {
  assert.equal(relationName({ name: "Fabryka A" }), "Fabryka A");
  assert.equal(relationName([{ name: "Operator" }]), "Operator");
  assert.equal(relationName([]), null);
  assert.equal(relationName(null), null);
});
