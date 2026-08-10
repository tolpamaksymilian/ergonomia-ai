import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { join } from "node:path";

export type PipelinePreflightCheck = {
  code: string;
  status: "OK" | "WARNING" | "ERROR";
  message: string;
};

export type PipelineHealth = {
  schema_version: "1.0";
  supervisor_version: string;
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
};

const root = process.cwd();
const healthPath = join(root, ".runtime", "worker-health.json");
const lockPath = join(root, ".runtime", "pipeline-supervisor.lock");
const stopRequestPath = join(root, ".runtime", "pipeline-supervisor.stop");

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

export async function readPipelineHealth(): Promise<PipelineHealth> {
  try {
    const value: unknown = JSON.parse(await readFile(healthPath, "utf8"));
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
    return {
      schema_version: "1.0",
      supervisor_version: textOrNull(raw.supervisor_version) ?? "unknown",
      status: safeStatus(raw.status),
      state: textOrNull(raw.state) ?? "unknown",
      supervisor_pid: numberOrNull(raw.supervisor_pid),
      pipeline_pid: numberOrNull(raw.pipeline_pid),
      started_at: textOrNull(raw.started_at),
      last_heartbeat_at: textOrNull(raw.last_heartbeat_at),
      analysis_id: textOrNull(raw.analysis_id),
      stage: textOrNull(raw.stage),
      last_progress_at: textOrNull(raw.last_progress_at),
      restart_count: typeof raw.restart_count === "number" && Number.isInteger(raw.restart_count) && raw.restart_count >= 0 ? raw.restart_count : 0,
      preflight_status: preflightStatus,
      preflight,
      last_error: error && typeof error.code === "string" && typeof error.message === "string"
        ? { code: error.code.slice(0, 80), message: error.message.slice(0, 300), at: textOrNull(error.at) ?? undefined }
        : null,
    };
  } catch {
    return {
      schema_version: "1.0", supervisor_version: "unknown", status: "offline", state: "heartbeat_missing",
      supervisor_pid: null, pipeline_pid: null, started_at: null, last_heartbeat_at: null, analysis_id: null,
      stage: null, last_progress_at: null, restart_count: 0, preflight_status: "UNKNOWN", preflight: [], last_error: null,
    };
  }
}

function pythonExecutable() {
  return process.platform === "win32"
    ? join(root, "worker", ".venv", "Scripts", "python.exe")
    : join(root, "worker", ".venv", "bin", "python");
}

async function readSupervisorLockPid() {
  try {
    const value: unknown = JSON.parse(await readFile(lockPath, "utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    return numberOrNull((value as Record<string, unknown>).pid);
  } catch {
    return null;
  }
}

function heartbeatIsFresh(value: string | null) {
  if (!value) return false;
  const age = Date.now() - Date.parse(value);
  return Number.isFinite(age) && age >= 0 && age <= 15_000;
}

export async function startPipelineSupervisor({ restart = false }: { restart?: boolean } = {}) {
  if (!localWorkerControlAllowed()) throw new Error("LOCAL_WORKER_CONTROL_DISABLED");
  const current = await readPipelineHealth();
  if (restart && current.supervisor_pid) {
    const lockPid = await readSupervisorLockPid();
    if (lockPid !== null && lockPid !== current.supervisor_pid) {
      throw new Error("SUPERVISOR_IDENTITY_MISMATCH");
    }
    if (lockPid === current.supervisor_pid) {
      await mkdir(join(root, ".runtime"), { recursive: true });
      await writeFile(stopRequestPath, `${Date.now()}\n`, { encoding: "utf8" });
      const deadline = Date.now() + 10_000;
      while (existsSync(lockPath) && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 150));
      }
      if (existsSync(lockPath)) {
        try {
          process.kill(current.supervisor_pid, "SIGTERM");
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
        }
        throw new Error("SUPERVISOR_STOP_TIMEOUT");
      }
    }
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
