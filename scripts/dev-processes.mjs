import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { posix, win32 } from "node:path";

export class ManagedProcessStartError extends Error {
  constructor(startupCode, label, cause) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    super(`${label}: ${detail}`, { cause });
    this.name = "ManagedProcessStartError";
    this.startupCode = startupCode;
    this.detail = detail;
  }
}

export function resolveNextProcess({
  repoRoot,
  nodeExecutable = process.execPath,
  platform = process.platform,
  port = 3000,
  pathExists = existsSync,
}) {
  const pathApi = platform === "win32" ? win32 : posix;
  const nextCli = pathApi.resolve(repoRoot, "node_modules", "next", "dist", "bin", "next");
  if (!pathExists(nextCli)) {
    throw new ManagedProcessStartError(
      "DEV_WEB_CLI_MISSING",
      "Next.js",
      new Error(`Nie znaleziono lokalnego CLI: ${nextCli}`),
    );
  }
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new ManagedProcessStartError(
      "DEV_WEB_PORT_INVALID",
      "Next.js",
      new Error(`Niepoprawny port: ${port}`),
    );
  }
  return {
    command: nodeExecutable,
    args: [nextCli, "dev", "--port", String(port)],
  };
}

export function resolvePythonProcess({
  repoRoot,
  platform = process.platform,
  pathExists = existsSync,
}) {
  const pathApi = platform === "win32" ? win32 : posix;
  const pythonExecutable = platform === "win32"
    ? pathApi.resolve(repoRoot, "worker", ".venv", "Scripts", "python.exe")
    : pathApi.resolve(repoRoot, "worker", ".venv", "bin", "python");
  if (!pathExists(pythonExecutable)) {
    throw new ManagedProcessStartError(
      "PIPELINE_PYTHON_MISSING",
      "Pipeline Supervisor",
      new Error(`Nie znaleziono interpretera: ${pythonExecutable}`),
    );
  }
  return {
    command: pythonExecutable,
    args: [pathApi.resolve(repoRoot, "worker", "src", "pipeline_supervisor.py")],
  };
}

export function spawnManagedProcess({
  label,
  startupCode,
  command,
  args,
  cwd,
  env = process.env,
  onExit,
  onRuntimeError,
  spawnImplementation = spawn,
}) {
  if (typeof command !== "string" || command.trim() === "") {
    return Promise.reject(new ManagedProcessStartError(
      startupCode,
      label,
      new Error("Pusta komenda procesu"),
    ));
  }

  return new Promise((resolvePromise, rejectPromise) => {
    let child;
    try {
      child = spawnImplementation(command, args, {
        cwd,
        env,
        stdio: "inherit",
        windowsHide: true,
        shell: false,
      });
    } catch (error) {
      rejectPromise(new ManagedProcessStartError(startupCode, label, error));
      return;
    }

    let started = false;
    child.once("spawn", () => {
      started = true;
      resolvePromise(child);
    });
    child.on("error", (error) => {
      const managedError = new ManagedProcessStartError(startupCode, label, error);
      if (!started) {
        rejectPromise(managedError);
        return;
      }
      onRuntimeError?.(managedError, child);
    });
    child.on("exit", (code, signal) => onExit?.(code, signal, child));
  });
}

export function runtimeSupervisorMatches({ health, lock, repoRoot, now = Date.now(), maximumAgeMs = 15_000 }) {
  const heartbeat = Date.parse(health?.last_heartbeat_at);
  return (
    Number.isInteger(health?.supervisor_pid)
    && lock?.pid === health.supervisor_pid
    && typeof health?.supervisor_instance_id === "string"
    && health.supervisor_instance_id.length > 0
    && lock?.instance_id === health.supervisor_instance_id
    && typeof lock?.repository_root === "string"
    && win32.normalize(lock.repository_root).toLowerCase() === win32.normalize(repoRoot).toLowerCase()
    && Number.isFinite(heartbeat)
    && now - heartbeat >= 0
    && now - heartbeat <= maximumAgeMs
    && ["online", "degraded", "restarting"].includes(health?.status)
  );
}

export function supervisorRestartDelay(attempt) {
  const delays = [500, 1_500, 4_000];
  return Number.isInteger(attempt) && attempt >= 1 && attempt <= delays.length
    ? delays[attempt - 1]
    : null;
}
