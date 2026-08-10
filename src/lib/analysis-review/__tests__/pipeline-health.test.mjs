import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { isLocalRequest, localWorkerControlAllowed } from "../../pipeline-health.ts";


test("worker process control is disabled in production and Vercel", { concurrency: false }, () => {
  const snapshot = {
    allowed: process.env.ALLOW_LOCAL_WORKER_CONTROL,
    node: process.env.NODE_ENV,
    vercel: process.env.VERCEL,
    vercelEnv: process.env.VERCEL_ENV,
  };
  try {
    process.env.ALLOW_LOCAL_WORKER_CONTROL = "true";
    process.env.NODE_ENV = "production";
    delete process.env.VERCEL;
    delete process.env.VERCEL_ENV;
    assert.equal(localWorkerControlAllowed(), false);
    process.env.NODE_ENV = "development";
    process.env.VERCEL = "1";
    assert.equal(localWorkerControlAllowed(), false);
    delete process.env.VERCEL;
    assert.equal(localWorkerControlAllowed(), true);
  } finally {
    restore("ALLOW_LOCAL_WORKER_CONTROL", snapshot.allowed);
    restore("NODE_ENV", snapshot.node);
    restore("VERCEL", snapshot.vercel);
    restore("VERCEL_ENV", snapshot.vercelEnv);
  }
});

test("health endpoint accepts only loopback hostnames", () => {
  assert.equal(isLocalRequest(new Request("http://localhost/api/system/pipeline-health")), true);
  assert.equal(isLocalRequest(new Request("http://127.0.0.1/api/system/pipeline-health")), true);
  assert.equal(isLocalRequest(new Request("https://example.com/api/system/pipeline-health")), false);
});

test("health route never returns environment credentials", async () => {
  const source = await readFile(new URL("../../../app/api/system/pipeline-health/route.ts", import.meta.url), "utf8");
  assert.equal(source.includes("SUPABASE_SECRET_KEY"), false);
  assert.equal(source.includes("process.env.NEXT_PUBLIC_SUPABASE"), false);
  assert.match(source, /requireUser\(\)/);
  assert.match(source, /profile\?\.role === "admin"/);
});

function restore(name, value) {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}

