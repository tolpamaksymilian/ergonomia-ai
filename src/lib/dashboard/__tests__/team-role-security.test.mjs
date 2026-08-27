import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const baseMigrationUrl = new URL("../../../../supabase/migrations/20260825190000_add_company_dashboard_management.sql", import.meta.url);
const teamRoleMigrationUrl = new URL("../../../../supabase/migrations/20260827120000_add_company_team_roles.sql", import.meta.url);

test("company administrators cannot grant the app superadministrator role", async () => {
  const sql = await readFile(teamRoleMigrationUrl, "utf8");
  assert.match(sql, /p_company_role public\.company_member_role/);
  assert.doesNotMatch(sql, /set\s+role\s*=/i);
  assert.doesNotMatch(sql, /p_(app|system)_role/i);
});

test("member updates remain scoped to the managed company", async () => {
  const [baseSql, teamSql] = await Promise.all([readFile(baseMigrationUrl, "utf8"), readFile(teamRoleMigrationUrl, "utf8")]);
  assert.match(baseSql, /p\.company_id = p_company_id[\s\S]+p\.company_role = 'admin'/);
  assert.match(teamSql, /if not public\.can_manage_company\(p_company_id\)/);
  assert.match(teamSql, /company_id = p_company_id or public\.is_admin\(\)/);
});

test("team role is informational and never participates in authorization", async () => {
  const [baseSql, teamSql] = await Promise.all([readFile(baseMigrationUrl, "utf8"), readFile(teamRoleMigrationUrl, "utf8")]);
  const canManage = baseSql.match(/create or replace function public\.can_manage_company[\s\S]+?\$\$;/i)?.[0] ?? "";
  assert.doesNotMatch(canManage, /team_role/);
  assert.match(teamSql, /team_role = nullif\(btrim\(p_team_role\), ''\)/);
  assert.doesNotMatch(teamSql, /team_role[\s\S]{0,80}(is_admin|can_manage_company)/i);
});

test("reviewer with Manager team role does not become an administrator", async () => {
  const baseSql = await readFile(baseMigrationUrl, "utf8");
  assert.match(baseSql, /p\.company_role = 'admin'::public\.company_member_role/);
  assert.doesNotMatch(baseSql, /p\.company_role in \('admin',\s*'reviewer'\)/i);
});
