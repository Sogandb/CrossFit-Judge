/**
 * Manages the Python CrossFit Judge engine as a child process.
 * Lazy-start on the first API request; auto-restart after crashes.
 * Uses the service venv when present (falls back to system python3).
 */
import { spawn, type ChildProcess } from "child_process";
import path from "path";
import fs from "fs";

const PYTHON_PORT = 8001;
const SERVICE_DIR = path.join(process.cwd(), "mini-services", "crossfit-judge");

/**
 * MediaPipe needs libEGL.so.1 / libGLESv2.so.2 even for CPU inference. On
 * hosts without the system packages we fall back to the bundled Chrome
 * libraries (v1 trick) through a compat dir of versioned symlinks.
 */
function extraLibPaths(): string[] {
  const found: string[] = [];
  const compatDir = path.join(process.cwd(), ".zscripts", "pylibs");
  if (fs.existsSync(path.join(compatDir, "libEGL.so.1"))) {
    found.push(compatDir);
  }
  const browsers = "/home/z/.agent-browser/browsers";
  try {
    for (const entry of fs.readdirSync(browsers, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const dir = path.join(browsers, entry.name);
      if (fs.existsSync(path.join(dir, "libEGL.so"))) found.push(dir);
    }
  } catch { /* dir absent on this host */ }
  return found;
}

function venvPython(): string {
  const candidates = [
    // Wodx deployment: setup.sh creates a service-local venv
    path.join(SERVICE_DIR, "venv", "bin", "python"),
    path.join(SERVICE_DIR, "venv", "Scripts", "python.exe"),
    // sandbox / dev fallbacks
    path.join(process.cwd(), ".zscripts", "pyvenv", "bin", "python"),
    "/home/z/.venv/bin/python",
  ];
  for (const p of candidates) if (fs.existsSync(p)) return p;
  return "python3";
}

let pyProcess: ChildProcess | null = null;
let startPromise: Promise<void> | null = null;

async function isServerAlive(): Promise<boolean> {
  try {
    const res = await fetch(`http://127.0.0.1:${PYTHON_PORT}/api/health`, {
      signal: AbortSignal.timeout(1500),
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function waitForServer(timeoutMs = 90000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isServerAlive()) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("سرویس تحلیل پایتون در زمان مجاز راه‌اندازی نشد");
}

function spawnServer(): ChildProcess {
  const env = {
    ...process.env,
    LD_LIBRARY_PATH: [...extraLibPaths(), process.env.LD_LIBRARY_PATH || ""]
      .filter(Boolean).join(":"),
    MEDIAPIPE_DISABLE_GPU: "1",
    GLOG_minloglevel: "2",
    LIBGL_ALWAYS_SOFTWARE: "1",
    EGL_PLATFORM: "surfaceless",
    HOME: process.env.HOME || "/home/z",
  };
  const proc = spawn(venvPython(), ["-m", "uvicorn", "main:app",
    "--host", "127.0.0.1", "--port", String(PYTHON_PORT),
    "--log-level", "warning"], {
    cwd: SERVICE_DIR,
    env,
    stdio: ["ignore", "pipe", "pipe"],
    detached: false,
  });
  proc.on("exit", (code, signal) => {
    console.error(`[judge-engine] exited code=${code} signal=${signal}`);
    pyProcess = null;
    startPromise = null;
  });
  proc.stdout?.on("data", (d: Buffer) => {
    const t = d.toString();
    if (!/absl::|W0000|ERR:/.test(t)) process.stdout.write(`[py] ${t}`);
  });
  proc.stderr?.on("data", (d: Buffer) => {
    const t = d.toString();
    if (!/absl::|W0000/.test(t)) process.stderr.write(`[py!] ${t}`);
  });
  return proc;
}

export async function ensureServer(): Promise<void> {
  if (await isServerAlive()) return;
  if (pyProcess) pyProcess = null;
  if (startPromise) return startPromise;
  startPromise = (async () => {
    if (await isServerAlive()) return;
    pyProcess = spawnServer();
    await waitForServer();
  })();
  try {
    await startPromise;
  } catch (e) {
    startPromise = null;
    throw e;
  }
}
