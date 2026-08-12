import { createConnection, createServer } from "node:net";
import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

import {
  ManagedProcessStartError,
  resolveNextProcess,
  resolvePythonProcess,
  spawnManagedProcess,
} from "./dev-processes.mjs";

const root = resolve(import.meta.dirname, "..");
const runtimeDirectory = join(root, ".runtime");
const stopRequestPath = join(runtimeDirectory, "pipeline-supervisor.stop");
const healthPath = join(runtimeDirectory, "worker-health.json");
const supervisorLockPath = join(runtimeDirectory, "pipeline-supervisor.lock");
const webPort = parseWebPort(process.env.PORT);
const children = [];
let shuttingDown = false;
let runtimeSupervisorPid = null;

function parseWebPort(value) {
  if (value === undefined || value.trim() === "") return 3000;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 65_535
    ? parsed
    : Number.NaN;
}

function processIsRunning(child) {
  return child.exitCode === null && child.signalCode === null;
}

function processDetail(error) {
  if (error instanceof ManagedProcessStartError) return error.detail;
  return error instanceof Error ? error.message : String(error);
}

function logStartError(scope, error, fallbackCode) {
  console.error(`[${scope}] Nie udało się uruchomić ${scope === "WEB" ? "Next.js" : "Pipeline Supervisor"}`);
  console.error(`Kod: ${error instanceof ManagedProcessStartError ? error.startupCode : fallbackCode}`);
  console.error(`Szczegóły: ${processDetail(error)}`);
}

async function portIsAvailable(port) {
  if (!Number.isInteger(port)) return false;
  return new Promise((resolvePromise, rejectPromise) => {
    const server = createServer();
    server.unref();
    server.once("error", (error) => {
      if (["EADDRINUSE", "EACCES"].includes(error.code)) {
        resolvePromise(false);
        return;
      }
      rejectPromise(error);
    });
    server.listen({ host: "127.0.0.1", port, exclusive: true }, () => {
      server.close((error) => error ? rejectPromise(error) : resolvePromise(true));
    });
  });
}

async function waitForWeb(port, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const connected = await new Promise((resolvePromise) => {
      const socket = createConnection({ host: "127.0.0.1", port });
      socket.setTimeout(500);
      socket.once("connect", () => {
        socket.destroy();
        resolvePromise(true);
      });
      socket.once("timeout", () => {
        socket.destroy();
        resolvePromise(false);
      });
      socket.once("error", () => resolvePromise(false));
    });
    if (connected) return true;
    await new Promise((resolveWait) => setTimeout(resolveWait, 150));
  }
  return false;
}

async function waitForWorkerHealth(startedAfterMs, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const health = JSON.parse(await readFile(healthPath, "utf8"));
      const heartbeatMs = Date.parse(health?.last_heartbeat_at);
      if (
        Number.isInteger(health?.supervisor_pid)
        && Number.isFinite(heartbeatMs)
        && heartbeatMs >= startedAfterMs - 1_000
        && ["online", "degraded", "crash_loop"].includes(health?.status)
      ) {
        return health;
      }
    } catch (error) {
      if (error?.code !== "ENOENT" && !(error instanceof SyntaxError)) throw error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 200));
  }
  return null;
}

function requestShutdown(child, signal) {
  if (!processIsRunning(child)) return;
  try {
    child.kill(signal);
  } catch (error) {
    if (error?.code !== "ESRCH") {
      console.error(`[DEV] Nie udało się zatrzymać PID ${child.pid}: ${processDetail(error)}`);
    }
  }
}

async function cleanupOwnedSupervisorLock() {
  const supervisor = children.find(({ label }) => label === "Pipeline Supervisor")?.child;
  if (!supervisor || processIsRunning(supervisor)) return;
  try {
    const lock = JSON.parse(await readFile(supervisorLockPath, "utf8"));
    if (runtimeSupervisorPid !== null && lock?.pid === runtimeSupervisorPid) {
      await unlink(supervisorLockPath);
    }
  } catch (error) {
    if (error?.code !== "ENOENT" && !(error instanceof SyntaxError)) {
      console.warn(`[WORKER] Nie udało się sprawdzić locka PID ${supervisor.pid}: ${processDetail(error)}`);
    }
  }
}

async function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log("\n[DEV] Zatrzymywanie środowiska...");
  await mkdir(runtimeDirectory, { recursive: true }).catch(() => undefined);
  await writeFile(stopRequestPath, `${Date.now()}\n`, "utf8").catch(() => undefined);

  for (const { label, child } of children) {
    if (label !== "Pipeline Supervisor") requestShutdown(child, "SIGTERM");
  }
  const deadline = Date.now() + 12_000;
  while (children.some(({ child }) => processIsRunning(child)) && Date.now() < deadline) {
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  for (const { child } of children) requestShutdown(child, "SIGKILL");
  const forceDeadline = Date.now() + 2_000;
  while (children.some(({ child }) => processIsRunning(child)) && Date.now() < forceDeadline) {
    await new Promise((resolveWait) => setTimeout(resolveWait, 50));
  }
  await cleanupOwnedSupervisorLock();
  console.log("[DEV] Środowisko zatrzymane.");
  process.exit(exitCode);
}

function childExitHandler(label) {
  return (code, signal) => {
    if (shuttingDown) return;
    if (label === "Pipeline Supervisor") {
      console.error(`[WORKER] Pipeline Supervisor zakończył się (${signal ?? code ?? "unknown"}). Next.js pozostaje dostępny z diagnostyką.`);
      return;
    }
    console.error(`[WEB] Next.js zakończył się (${signal ?? code ?? "unknown"}). Zatrzymuję środowisko.`);
    void shutdown(code ?? 1);
  };
}

function childRuntimeErrorHandler(scope, fallbackCode) {
  return (error) => {
    logStartError(scope, error, fallbackCode);
    void shutdown(1);
  };
}

async function startManaged(label, scope, startupCode, specification) {
  const child = await spawnManagedProcess({
    label,
    startupCode,
    ...specification,
    cwd: root,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    onExit: childExitHandler(label),
    onRuntimeError: childRuntimeErrorHandler(scope, startupCode),
  });
  children.push({ label, child });
  return child;
}

async function main() {
  console.log(`[DEV] Ergonomia AI 0.14.0-beta.1`);
  console.log(`[DEV] Node: ${process.version}`);
  console.log(`[DEV] Platform: ${process.platform}`);
  console.log(`[DEV] Repository: ${root}\n`);

  if (!await portIsAvailable(webPort)) {
    console.error(`[WEB] Port ${Number.isInteger(webPort) ? webPort : process.env.PORT} jest już zajęty lub niedostępny.`);
    console.error("Kod: DEV_WEB_PORT_UNAVAILABLE");
    process.exitCode = 1;
    return;
  }

  let web;
  try {
    const nextProcess = resolveNextProcess({ repoRoot: root, port: webPort });
    console.log("[WEB] Starting Next.js...");
    web = await startManaged("Next.js", "WEB", "DEV_WEB_START_FAILED", nextProcess);
    console.log(`[WEB] Next.js process running (PID ${web.pid})`);
  } catch (error) {
    logStartError("WEB", error, "DEV_WEB_START_FAILED");
    await shutdown(1);
    return;
  }

  let worker;
  const workerLaunchStartedAt = Date.now();
  try {
    const pythonProcess = resolvePythonProcess({ repoRoot: root });
    console.log("[WORKER] Starting Pipeline Supervisor...");
    worker = await startManaged(
      "Pipeline Supervisor",
      "WORKER",
      "PIPELINE_SUPERVISOR_START_FAILED",
      pythonProcess,
    );
    console.log(`[WORKER] Pipeline Supervisor process running (PID ${worker.pid})`);
  } catch (error) {
    logStartError("WORKER", error, "PIPELINE_SUPERVISOR_START_FAILED");
    await shutdown(1);
    return;
  }

  const [webReady, workerHealth] = await Promise.all([
    waitForWeb(webPort),
    waitForWorkerHealth(workerLaunchStartedAt),
  ]);
  if (!webReady) {
    logStartError("WEB", new Error(`Port ${webPort} nie zaczął odpowiadać w wyznaczonym czasie.`), "DEV_WEB_START_TIMEOUT");
    await shutdown(1);
    return;
  }
  console.log("[WEB] Next.js running");
  if (workerHealth) {
    runtimeSupervisorPid = workerHealth.supervisor_pid;
    console.log(`[WORKER] State: ${workerHealth.status.toUpperCase()}`);
  } else {
    console.warn("[WORKER] Proces działa, ale heartbeat nie jest jeszcze dostępny.");
  }
  console.log("\n[DEV] System ready");
  console.log(`[DEV] http://localhost:${webPort}`);
}

process.on("SIGINT", () => void shutdown(0));
process.on("SIGTERM", () => void shutdown(0));
process.on("SIGBREAK", () => void shutdown(0));

await main();
