import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { join, resolve } from "node:path";

export type PipelinePreflightCheck = {
  code: string;
  status: "OK" | "WARNING" | "ERROR";
  message: string;
};

export type PipelineHealth = {
  schema_version: "1.0";
  supervisor_version: string;
  supervisor_instance_id: string | null;
  status: "online" | "offline" | "degraded" | "restarting" | "crash_loop" | "unknown";
  state: string;
  supervisor_pid: number | null;
  pipeline_pid: number | null;
  started_at: string | null;
  last_heartbeat_at: string | null;
  analysis_id: string | null;
  stage: string | null;
  last_progress_at: string | null;
  restart_count: number;
  preflight_status: "OK" | "WARNING" | "ERROR" | "UNKNOWN";
  preflight: PipelinePreflightCheck[];
  last_error: { code: string; message: string; at?: string } | null;
  health_persistence: "healthy" | "degraded" | "unknown";
  health_write_failures_total: number;
  health_write_failures_consecutive: number;
  health_replace_retries_total: number;
  last_health_write_attempt_at: string | null;
  last_health_write_success_at: string | null;
  last_health_write_error: string | null;
  last_health_write_error_at: string | null;
  health_read_status: "current" | "cached" | "unavailable";
  health_unavailable_since: string | null;
};

const root = process.cwd();
const healthPath = join(root, ".runtime", "worker-health.json");
const lockPath = join(root, ".runtime", "pipeline-supervisor.lock");
const stopRequestPath = join(root, ".runtime", "pipeline-supervisor.stop");
const healthReadRetryDelaysMs = [0, 20, 50] as const;
let lastKnownHealth: PipelineHealth | null = null;
let healthUnavailableSince: string | null = null;

export function localWorkerControlAllowed() {
  return (
    process.env.ALLOW_LOCAL_WORKER_CONTROL === "true" &&
    process.env.VERCEL !== "1" &&
    !process.env.VERCEL_ENV &&
    process.env.NODE_ENV !== "production"
  );
}

export function isLocalRequest(request: Request) {
  const hostname = new URL(request.url).hostname.toLowerCase();
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

function numberOrNull(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

function textOrNull(value: unknown) {
  return typeof value === "string" && value.length <= 500 ? value : null;
}

function safeStatus(value: unknown): PipelineHealth["status"] {
  return ["online", "offline", "degraded", "restarting", "crash_loop"].includes(String(value))
    ? (value as PipelineHealth["status"])
    : "unknown";
}

function nonNegativeInteger(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : 0;
}

function safePersistence(value: unknown): PipelineHealth["health_persistence"] {
  return value === "healthy" || value === "degraded" ? value : "unknown";
}

export async function readRuntimeJsonWithRetry(
  path: string,
  {
    reader = readFile,
    delays = healthReadRetryDelaysMs,
    wait = (milliseconds: number) => new Promise<void>((resolve) => setTimeout(resolve, milliseconds)),
  }: {
    reader?: typeof readFile;
    delays?: readonly number[];
    wait?: (milliseconds: number) => Promise<void>;
  } = {},
): Promise<unknown> {
  if (delays.length === 0) throw new Error("health_read_retry_delays_empty");
  let lastError: unknown = new Error("health_read_failed");
  for (const [index, delay] of delays.entries()) {
    if (delay > 0) await wait(delay);
    try {
      return JSON.parse(await reader(path, "utf8"));
    } catch (error) {
      lastError = error;
      const code = error && typeof error === "object" && "code" in error
        ? String((error as NodeJS.ErrnoException).code)
        : null;
      const retryable = error instanceof SyntaxError || ["ENOENT", "EACCES", "EPERM", "EBUSY"].includes(code ?? "");
      if (!retryable || index === delays.length - 1) throw error;
    }
  }
  throw lastError;
}

function unavailableHealth(state: string): PipelineHealth {
  healthUnavailableSince ??= new Date().toISOString();
  return {
    schema_version: "1.0", supervisor_version: "unknown", supervisor_instance_id: null,
    status: "unknown", state, supervisor_pid: null, pipeline_pid: null, started_at: null,
    last_heartbeat_at: null, analysis_id: null, stage: null, last_progress_at: null,
    restart_count: 0, preflight_status: "UNKNOWN", preflight: [], last_error: null,
    health_persistence: "unknown", health_write_failures_total: 0,
    health_write_failures_consecutive: 0, health_replace_retries_total: 0,
    last_health_write_attempt_at: null, last_health_write_success_at: null,
    last_health_write_error: null, last_health_write_error_at: null,
    health_read_status: "unavailable", health_unavailable_since: healthUnavailableSince,
  };
}

export async function readPipelineHealth(): Promise<PipelineHealth> {
  try {
    const value = await readRuntimeJsonWithRetry(healthPath);
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_health_shape");
    const raw = value as Record<string, unknown>;
    const preflight = Array.isArray(raw.preflight)
      ? raw.preflight.flatMap((entry): PipelinePreflightCheck[] => {
          if (!entry || typeof entry !== "object" || Array.isArray(entry)) return [];
          const item = entry as Record<string, unknown>;
          const status = String(item.status);
          if (typeof item.code !== "string" || typeof item.message !== "string" || !["OK", "WARNING", "ERROR"].includes(status)) return [];
          return [{ code: item.code.slice(0, 80), status: status as PipelinePreflightCheck["status"], message: item.message.slice(0, 240) }];
        })
      : [];
    const error = raw.last_error && typeof raw.last_error === "object" && !Array.isArray(raw.last_error)
      ? raw.last_error as Record<string, unknown>
      : null;
    const preflightStatus = ["OK", "WARNING", "ERROR"].includes(String(raw.preflight_status))
      ? raw.preflight_status as PipelineHealth["preflight_status"]
      : "UNKNOWN";
    const result: PipelineHealth = {
      schema_version: "1.0",
      supervisor_version: textOrNull(raw.supervisor_version) ?? "unknown",
      supervisor_instance_id: textOrNull(raw.supervisor_instance_id),
      status: safeStatus(raw.status),
      state: textOrNull(raw.state) ?? "unknown",
      supervisor_pid: numberOrNull(raw.supervisor_pid),
      pipeline_pid: numberOrNull(raw.pipeline_pid),
      started_at: textOrNull(raw.started_at),
      last_heartbeat_at: textOrNull(raw.last_heartbeat_at),
      analysis_id: textOrNull(raw.analysis_id),
      stage: textOrNull(raw.stage),
      last_progress_at: textOrNull(raw.last_progress_at),
      restart_count: nonNegativeInteger(raw.restart_count),
      preflight_status: preflightStatus,
      preflight,
      last_error: error && typeof error.code === "string" && typeof error.message === "string"
        ? { code: error.code.slice(0, 80), message: error.message.slice(0, 300), at: textOrNull(error.at) ?? undefined }
        : null,
      health_persistence: safePersistence(raw.health_persistence),
      health_write_failures_total: nonNegativeInteger(raw.health_write_failures_total),
      health_write_failures_consecutive: nonNegativeInteger(raw.health_write_failures_consecutive),
      health_replace_retries_total: nonNegativeInteger(raw.health_replace_retries_total),
      last_health_write_attempt_at: textOrNull(raw.last_health_write_attempt_at),
      last_health_write_success_at: textOrNull(raw.last_health_write_success_at),
      last_health_write_error: textOrNull(raw.last_health_write_error),
      last_health_write_error_at: textOrNull(raw.last_health_write_error_at),
      health_read_status: "current",
      health_unavailable_since: null,
    };
    lastKnownHealth = result;
    healthUnavailableSince = null;
    return result;
  } catch {
    healthUnavailableSince ??= new Date().toISOString();
    if (lastKnownHealth && heartbeatIsFresh(lastKnownHealth.last_heartbeat_at, 30_000)) {
      return {
        ...lastKnownHealth,
        health_persistence: "degraded",
        health_read_status: "cached",
        health_unavailable_since: healthUnavailableSince,
      };
    }
    return unavailableHealth("heartbeat_unavailable");
  }
}

function pythonExecutable() {
  return process.platform === "win32"
    ? join(root, "worker", ".venv", "Scripts", "python.exe")
    : join(root, "worker", ".venv", "bin", "python");
}

async function readSupervisorLock() {
  try {
    const value = await readRuntimeJsonWithRetry(lockPath);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const raw = value as Record<string, unknown>;
    return {
      pid: numberOrNull(raw.pid),
      instanceId: textOrNull(raw.instance_id),
      repositoryRoot: textOrNull(raw.repository_root),
    };
  } catch {
    return null;
  }
}

function heartbeatIsFresh(value: string | null, maximumAgeMs = 15_000) {
  if (!value) return false;
  const age = Date.now() - Date.parse(value);
  return Number.isFinite(age) && age >= 0 && age <= maximumAgeMs;
}

function pidIsRunning(pid: number | null) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

async function waitForSupervisorExit(pid: number, timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!pidIsRunning(pid) && !existsSync(lockPath)) return true;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return !pidIsRunning(pid) && !existsSync(lockPath);
}

export async function startPipelineSupervisor({ restart = false }: { restart?: boolean } = {}) {
  if (!localWorkerControlAllowed()) throw new Error("LOCAL_WORKER_CONTROL_DISABLED");
  const current = await readPipelineHealth();
  const lock = await readSupervisorLock();
  if (restart && current.supervisor_pid) {
    if (lock && lock.pid !== null && lock.pid !== current.supervisor_pid) {
      throw new Error("SUPERVISOR_IDENTITY_MISMATCH");
    }
    if (lock?.repositoryRoot && resolve(lock.repositoryRoot) !== root) {
      throw new Error("SUPERVISOR_REPOSITORY_MISMATCH");
    }
    if (
      lock?.instanceId
      && current.supervisor_instance_id
      && lock.instanceId !== current.supervisor_instance_id
    ) {
      throw new Error("SUPERVISOR_INSTANCE_MISMATCH");
    }
    if (lock?.pid === current.supervisor_pid) {
      await mkdir(join(root, ".runtime"), { recursive: true });
      await writeFile(stopRequestPath, `${Date.now()}\n`, { encoding: "utf8" });
      if (!await waitForSupervisorExit(current.supervisor_pid, 12_000)) {
        try {
          process.kill(current.supervisor_pid, "SIGTERM");
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
        }
        if (!await waitForSupervisorExit(current.supervisor_pid, 2_000)) {
          try {
            process.kill(current.supervisor_pid, "SIGKILL");
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
          }
          if (!await waitForSupervisorExit(current.supervisor_pid, 1_000)) {
            throw new Error("SUPERVISOR_STOP_TIMEOUT");
          }
        }
      }
    }
  } else if (
    lock?.pid
    && pidIsRunning(lock.pid)
    && (current.supervisor_pid === lock.pid || current.supervisor_pid === null)
  ) {
    return current;
  } else if (current.status === "online" && current.supervisor_pid && heartbeatIsFresh(current.last_heartbeat_at)) {
    return current;
  }
  const python = pythonExecutable();
  if (!existsSync(python)) throw new Error("WORKER_PYTHON_MISSING");
  const child = spawn(python, [join(root, "worker", "src", "pipeline_supervisor.py")], {
    cwd: root,
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });
  await new Promise<void>((resolve, reject) => {
    child.once("spawn", resolve);
    child.once("error", (error) => reject(new Error("PIPELINE_SUPERVISOR_START_FAILED", { cause: error })));
  });
  child.unref();
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
    const health = await readPipelineHealth();
    if (["online", "degraded", "crash_loop"].includes(health.status)) return health;
  }
  throw new Error("SUPERVISOR_HEARTBEAT_TIMEOUT");
}
