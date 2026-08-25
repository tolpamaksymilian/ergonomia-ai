import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const migrationUrl = new URL("../../../../supabase/migrations/20260825190000_add_company_dashboard_management.sql", import.meta.url);

test("company dashboard migration keeps tenant isolation and invite contracts", async () => {
  const sql = await readFile(migrationUrl, "utf8");
  assert.match(sql, /enable row level security/gi);
  assert.match(sql, /public\.can_manage_company\(company_id\)/g);
  assert.match(sql, /public\.current_company_id\(\)/g);
  assert.match(sql, /company_invitations_pending_email_uidx/g);
  assert.match(sql, /accept_my_company_invitation/g);
  assert.match(sql, /revoke all on function public\.manage_company_member/g);
});
