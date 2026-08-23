import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { win32, posix } from "node:path";
import test from "node:test";

import {
  ManagedProcessStartError,
  resolveNextProcess,
  resolvePythonProcess,
  runtimeSupervisorMatches,
  spawnManagedProcess,
  supervisorRestartDelay,
} from "./dev-processes.mjs";

test("Next.js uses the current Node executable without a cmd or shell", () => {
  const result = resolveNextProcess({
    repoRoot: "C:\\repo",
    nodeExecutable: "C:\\node\\node.exe",
    platform: "win32",
    port: 3000,
    pathExists: () => true,
  });
  assert.equal(result.command, "C:\\node\\node.exe");
  assert.equal(result.args.at(-3), "dev");
  assert.equal(result.args.at(-1), "3000");
  assert.doesNotMatch(result.command, /\.cmd$|\.bat$/i);
});

test("POSIX Next.js also uses the current Node executable", () => {
  const result = resolveNextProcess({
    repoRoot: "/repo",
    nodeExecutable: "/usr/bin/node",
    platform: "linux",
    port: 3000,
    pathExists: () => true,
  });
  assert.equal(result.command, "/usr/bin/node");
  assert.equal(result.args[0], "/repo/node_modules/next/dist/bin/next");
  assert.deepEqual(result.args.slice(1), ["dev", "--port", "3000"]);
});

test("Windows Python resolves to the virtual environment executable", () => {
  const result = resolvePythonProcess({
    repoRoot: "C:\\repo",
    platform: "win32",
    pathExists: () => true,
  });
  assert.equal(result.command, win32.resolve("C:\\repo", "worker", ".venv", "Scripts", "python.exe"));
  assert.equal(result.args[0], win32.resolve("C:\\repo", "worker", "src", "pipeline_supervisor.py"));
});

test("POSIX Python resolves to the virtual environment executable", () => {
  const result = resolvePythonProcess({
    repoRoot: "/repo",
    platform: "linux",
    pathExists: () => true,
  });
  assert.equal(result.command, posix.resolve("/repo", "worker", ".venv", "bin", "python"));
  assert.equal(result.args[0], posix.resolve("/repo", "worker", "src", "pipeline_supervisor.py"));
});

test("spawn errors use the stable startup code", async () => {
  const child = new EventEmitter();
  const started = spawnManagedProcess({
    label: "Next.js",
    startupCode: "DEV_WEB_START_FAILED",
    command: "node",
    args: [],
    cwd: "C:\\repo",
    spawnImplementation: () => {
      queueMicrotask(() => child.emit("error", Object.assign(new Error("spawn EINVAL"), { code: "EINVAL" })));
      return child;
    },
  });
  await assert.rejects(started, (error) => {
    assert.ok(error instanceof ManagedProcessStartError);
    assert.equal(error.startupCode, "DEV_WEB_START_FAILED");
    assert.match(error.detail, /spawn EINVAL/);
    return true;
  });
});

test("managed processes preserve cwd and env while keeping shell disabled", async () => {
  const child = new EventEmitter();
  child.pid = 123;
  let receivedOptions;
  const result = spawnManagedProcess({
    label: "Next.js",
    startupCode: "DEV_WEB_START_FAILED",
    command: "node",
    args: ["next", "dev"],
    cwd: "C:\\repo",
    env: { TEST_VALUE: "present" },
    spawnImplementation: (_command, _args, options) => {
      receivedOptions = options;
      queueMicrotask(() => child.emit("spawn"));
      return child;
    },
  });
  assert.equal(await result, child);
  assert.equal(receivedOptions.cwd, "C:\\repo");
  assert.equal(receivedOptions.env.TEST_VALUE, "present");
  assert.equal(receivedOptions.shell, false);
});

test("dev supervisor reuses only the same fresh repository instance", () => {
  const now = Date.parse("2026-08-21T10:00:00Z");
  const health = {
    supervisor_pid: 321,
    supervisor_instance_id: "instance-a",
    last_heartbeat_at: "2026-08-21T09:59:57Z",
    status: "online",
  };
  const lock = {
    pid: 321,
    instance_id: "instance-a",
    repository_root: "C:\\repo",
  };
  assert.equal(runtimeSupervisorMatches({ health, lock, repoRoot: "C:\\repo", now }), true);
  assert.equal(runtimeSupervisorMatches({ health, lock: { ...lock, instance_id: "other" }, repoRoot: "C:\\repo", now }), false);
  assert.equal(runtimeSupervisorMatches({ health, lock: { ...lock, repository_root: "C:\\other" }, repoRoot: "C:\\repo", now }), false);
});

test("dev supervisor restart policy is bounded and cannot rapid-loop", () => {
  assert.deepEqual([1, 2, 3].map(supervisorRestartDelay), [500, 1_500, 4_000]);
  assert.equal(supervisorRestartDelay(4), null);
  assert.equal(supervisorRestartDelay(0), null);
});
