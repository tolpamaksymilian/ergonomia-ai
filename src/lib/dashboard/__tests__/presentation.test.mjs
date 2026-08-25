import test from "node:test";
import assert from "node:assert/strict";

import {
  accountStatusLabel,
  companyRoleLabel,
  isDashboardPathActive,
  relationName,
} from "../presentation.ts";
import {
  adminDashboardNavigation,
  companyAdminNavigation,
  userDashboardNavigation,
} from "../../../config/dashboard-navigation.ts";

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

test("navigation passed across the server-client boundary is serializable", () => {
  const groups = [...userDashboardNavigation, companyAdminNavigation, ...adminDashboardNavigation];
  assert.doesNotThrow(() => structuredClone(groups));
  for (const group of groups) {
    for (const item of group.items) assert.equal(typeof item.icon, "string");
  }
});
