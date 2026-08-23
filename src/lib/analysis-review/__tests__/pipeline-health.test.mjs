import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { isLocalRequest, localWorkerControlAllowed, readRuntimeJsonWithRetry } from "../../pipeline-health.ts";


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

test("runtime health reader retries transient corrupt JSON and closes each read", async () => {
  let reads = 0;
  const value = await readRuntimeJsonWithRetry("health.json", {
    delays: [0, 0],
    wait: async () => undefined,
    reader: async () => {
      reads += 1;
      return reads === 1 ? "{partial" : '{"status":"online"}';
    },
  });
  assert.deepEqual(value, { status: "online" });
  assert.equal(reads, 2);
});

test("runtime health reader returns only a complete old or new document under replacement", async () => {
  const documents = ['{"generation":1}', '{"generation":2}'];
  let index = 0;
  for (let iteration = 0; iteration < 200; iteration += 1) {
    const parsed = await readRuntimeJsonWithRetry("health.json", {
      delays: [0],
      reader: async () => documents[index++ % documents.length],
    });
    assert.ok(parsed.generation === 1 || parsed.generation === 2);
  }
});

function restore(name, value) {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}
