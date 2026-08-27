import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  CUSTOM_TEAM_ROLE_VALUE,
  PREDEFINED_TEAM_ROLES,
  resolveTeamRole,
  teamRoleChoice,
} from "../team-roles.ts";

test("dashboard shell is dark-only and its topbar has no theme switch", async () => {
  const [css, topbar, settings] = await Promise.all([
    readFile(new URL("../../../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../../../components/dashboard/dashboard-topbar.tsx", import.meta.url), "utf8"),
    readFile(new URL("../../../app/panel/ustawienia/page.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(css, /\.dashboard-shell\s*{[\s\S]*color-scheme:\s*dark/);
  assert.doesNotMatch(topbar, /ThemeToggle|theme-toggle/);
  assert.doesNotMatch(settings, /Wygląd|Motyw jasny|light/i);
});

test("predefined and custom team roles resolve independently", () => {
  assert.ok(PREDEFINED_TEAM_ROLES.includes("Specjalista BHP"));
  assert.equal(resolveTeamRole("Manager", null), "Manager");
  assert.equal(resolveTeamRole(CUSTOM_TEAM_ROLE_VALUE, "Koordynator zmiany"), "Koordynator zmiany");
  assert.equal(resolveTeamRole(CUSTOM_TEAM_ROLE_VALUE, "  "), null);
  assert.equal(teamRoleChoice("Właściciel procesu"), CUSTOM_TEAM_ROLE_VALUE);
});

test("member and invitation forms keep system role, team role and position separate", async () => {
  const [team, invite, actions] = await Promise.all([
    readFile(new URL("../../../components/dashboard/team-management.tsx", import.meta.url), "utf8"),
    readFile(new URL("../../../components/dashboard/invite-user-form.tsx", import.meta.url), "utf8"),
    readFile(new URL("../../../app/admin/actions.ts", import.meta.url), "utf8"),
  ]);
  for (const source of [team, invite]) {
    assert.match(source, /name="company_role"/);
    assert.match(source, /name="team_role_choice"/);
    assert.match(source, /name="position_id"/);
  }
  assert.match(invite, /lockCompany[\s\S]+type="hidden" name="company_id"/);
  assert.match(actions, /manage_company_member_v2/);
  assert.match(actions, /resolveTeamRole/);
});
