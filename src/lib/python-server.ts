/**
 * Manages the Python CrossFit Judge engine as a child process.
 * Lazy-start on the first API request; auto-restart after crashes.
 * Uses the service venv when present (falls back to system python3).
 *
 * SELF-HEALING (survives sandbox resets): the analysis stack lives in the
 * venv + a few binary assets OUTSIDE git, and the sandbox has been observed
 * to reset overnight, wiping them (mediapipe, the pose model, the GLVND
 * libs). ensureDeps() verifies the heavy imports BEFORE spawning the
 * server and repairs them automatically:
 *   * missing python deps  → uv/pip install -r requirements.txt
 *   * missing pose model   → download from Google's model storage
 *   * missing GLVND libs   → download+extract the Debian runtime .debs
 * The GL libs and the pose model are ALSO vendored in git (pylibs/,
 * data/models/) so a git-restore reset brings them back with zero network.
 */
import { spawn, type ChildProcess } from "child_process";
import path from "path";
import fs from "fs";
import { pipeline } from "stream/promises";
import { Readable } from "node:stream";
import { createWriteStream } from "fs";

const PYTHON_PORT = 8001;
const SERVICE_DIR = path.join(process.cwd(), "mini-services", "crossfit-judge");
const REPO_PYLIBS = path.join(SERVICE_DIR, "pylibs");   // git-vendored GL libs
const LEGACY_PYLIBS = path.join(process.cwd(), ".zscripts", "pylibs");
const MODEL_PATH = path.join(SERVICE_DIR, "data", "models", "pose_landmarker_full.task");
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task";
const GLVND_BASE =
  "https://deb.debian.org/debian/pool/main/libg/libglvnd";
const GLVND_PKGS = ["libegl1", "libgles2", "libglx0", "libgl1", "libglvnd0"];
const GLVND_VER = "1.7.0-1+b2";

/**
 * MediaPipe needs libEGL.so.1 / libGLESv2.so.2 even for CPU inference. We
 * prefer the git-vendored Debian runtime libs, then the legacy sandbox
 * location, and finally fall back to the bundled Chrome libraries through
 * a compat dir of versioned symlinks.
 */
function extraLibPaths(): string[] {
  const found: string[] = [];
  for (const dir of [REPO_PYLIBS, LEGACY_PYLIBS]) {
    if (fs.existsSync(path.join(dir, "libEGL.so.1"))) found.push(dir);
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

// --------------------------------------------------------------------------- //
// Self-healing dependency bootstrap
// --------------------------------------------------------------------------- //

function run(cmd: string, args: string[], timeoutMs = 120_000): Promise<{ code: number; out: string }> {
  return new Promise((resolve) => {
    try {
      const p = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
      let out = "";
      const t = setTimeout(() => p.kill("SIGKILL"), timeoutMs);
      p.stdout?.on("data", (d) => { out += d; process.stdout.write(`[deps] ${d}`); });
      p.stderr?.on("data", (d) => { out += d; process.stderr.write(`[deps] ${d}`); });
      p.on("error", () => { clearTimeout(t); resolve({ code: 127, out }); });
      p.on("exit", (code) => { clearTimeout(t); resolve({ code: code ?? 1, out }); });
    } catch {
      resolve({ code: 127, out: "" });
    }
  });
}

async function download(to: string, url: string): Promise<void> {
  const res = await fetch(url, { redirect: "follow" });
  if (!res.ok || !res.body) throw new Error(`download ${url} → HTTP ${res.status}`);
  fs.mkdirSync(path.dirname(to), { recursive: true });
  const tmp = `${to}.part`;
  await pipeline(Readable.fromWeb(res.body as never), createWriteStream(tmp));
  fs.renameSync(tmp, to);
}

/** Verify the heavy python imports with the EXACT interpreter we will spawn. */
async function pythonDepsOk(): Promise<boolean> {
  const py = venvPython();
  const r = await run(py, ["-c", "import mediapipe, cv2, fastapi, uvicorn"], 30_000);
  return r.code === 0;
}

async function installPythonDeps(): Promise<boolean> {
  console.log("[judge-engine] python deps missing — installing requirements.txt …");
  const py = venvPython();
  const req = path.join(SERVICE_DIR, "requirements.txt");
  // uv first (fast), fall back to pip
  const viaUv = await run("uv", ["pip", "install", "--python", py, "-r", req], 600_000);
  if (viaUv.code === 0) return true;
  console.error("[judge-engine] uv install failed, trying pip …");
  const viaPip = await run(py, ["-m", "pip", "install", "-r", req], 600_000);
  return viaPip.code === 0;
}

function modelPresent(): boolean {
  return fs.existsSync(MODEL_PATH) && fs.statSync(MODEL_PATH).size > 1_000_000;
}

function glLibsPresent(dir: string): boolean {
  return fs.existsSync(path.join(dir, "libEGL.so.1"));
}

/** Download + extract the Debian GLVND runtime libs into pylibs/ (fallback
 *  when the git-vendored copies are absent). */
async function installGlLibs(dir: string): Promise<boolean> {
  console.log("[judge-engine] GLVND libs missing — downloading Debian runtime …");
  try {
    fs.mkdirSync(dir, { recursive: true });
    const tmp = fs.mkdtempSync("/tmp/glvnd-");
    for (const p of GLVND_PKGS) {
      const deb = path.join(tmp, `${p}.deb`);
      await download(deb, `${GLVND_BASE}/${p}_${GLVND_VER}_amd64.deb`);
      await run("bash", ["-c", `cd ${tmp} && dpkg-deb -x ${p}.deb ${tmp}/x 2>/dev/null || (ar x ${p}.deb && tar -xf data.tar.xz -C ${tmp}/x)`], 60_000);
    }
    const libDir = path.join(tmp, "x", "usr", "lib", "x86_64-linux-gnu");
    for (const f of fs.readdirSync(libDir)) {
      if (f.endsWith(".so") || f.includes(".so.")) {
        fs.copyFileSync(path.join(libDir, f), path.join(dir, f));
      }
    }
    return glLibsPresent(dir);
  } catch (e) {
    console.error("[judge-engine] GLVND download failed:", e);
    return false;
  }
}

let depsVerifiedAt = 0;
const DEPS_TTL_MS = 10 * 60_000; // re-verify at most every 10 min

/**
 * Repair the analysis environment before the server spawns. Cheap when
 * everything is present (one ~2 s import probe, TTL-cached); heavyweight
 * only right after a sandbox reset (install ≈ 60-120 s, model ≈ 10 s).
 */
export async function ensureDeps(): Promise<void> {
  if (Date.now() - depsVerifiedAt < DEPS_TTL_MS) return;
  const py = venvPython();

  // 1. python packages (mediapipe et al.)
  if (!(await pythonDepsOk())) {
    const ok = await installPythonDeps();
    if (!ok) throw new Error("نصب پیش‌نیازهای تحلیل (mediapipe) ناموفق بود");
    depsVerifiedAt = 0; // re-verify below after install
  }

  // 2. pose model (git-vendored usually — download is the fallback)
  if (!modelPresent()) {
    console.log("[judge-engine] pose model missing — downloading …");
    await download(MODEL_PATH, MODEL_URL);
    if (!modelPresent()) throw new Error("دانلود مدل تحلیل حرکت ناموفق بود");
  }

  // 3. GLVND runtime libs (git-vendored usually — download is the fallback)
  if (!glLibsPresent(REPO_PYLIBS) && !glLibsPresent(LEGACY_PYLIBS)) {
    await installGlLibs(REPO_PYLIBS);
    // non-fatal: the Chrome fallback may still work
  }

  // 4. final verification with the real interpreter
  if (!(await pythonDepsOk())) {
    throw new Error("محیط تحلیل پایتون سالم نیست (mediapipe)");
  }
  depsVerifiedAt = Date.now();
  console.log("[judge-engine] deps verified ✓",
    { py, model: modelPresent(), gl: glLibsPresent(REPO_PYLIBS) || glLibsPresent(LEGACY_PYLIBS) });
}

// --------------------------------------------------------------------------- //
// Server lifecycle
// --------------------------------------------------------------------------- //

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
    depsVerifiedAt = 0; // a crash may mean deps broke again → re-verify
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

let pyProcess: ChildProcess | null = null;
let startPromise: Promise<void> | null = null;
let warmupStartedAt = 0;

export interface ServerStatus {
  /** Engine responds on :8001 */
  alive: boolean;
  /** Install/spawn still in progress (e.g. right after a sandbox reset) */
  warming: boolean;
  /** How long the current warmup has been running (ms) */
  elapsedMs: number;
}

function _sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Ensure the Python engine is up — WITHOUT hanging the caller.
 *
 * Cold-start reality (measured after sandbox resets): when the venv was
 * wiped, ensureDeps() reinstalls ~40-120 s BEFORE uvicorn can even spawn.
 * A request that blocks on that gets killed by preview-tunnel timeouts
 * (the user sees a frozen 1% upload bar / a crash error). Instead:
 *
 *   * engine alive            → resolves immediately
 *   * warmup already running  → waits at most maxWaitMs, then reports
 *                               {warming:true} so the caller can answer
 *                               503 + warming_up and the CLIENT retries
 *                               politely while showing a preparing message
 *   * no warmup yet           → starts one (install + spawn) and waits
 *                               the same bounded time
 *   * warmup FAILED           → throws (caller returns an honest error)
 */
export async function ensureServer(maxWaitMs = 20_000): Promise<ServerStatus> {
  if (await isServerAlive()) return { alive: true, warming: false, elapsedMs: 0 };
  const started = Date.now();
  if (!startPromise) {
    warmupStartedAt = Date.now();
    startPromise = (async () => {
      if (await isServerAlive()) return;
      // SELF-HEALING GATE: repair the environment BEFORE spawning (a wiped
      // venv/model is exactly what kills analysis mid-run after resets).
      try {
        await ensureDeps();
      } catch (e) {
        startPromise = null;
        throw e;
      }
      pyProcess = spawnServer();
      await waitForServer();
    })();
    // A rejected warmup must not become an unhandled rejection for the
    // fire-and-forget callers; ensureServer re-throws per caller instead.
    startPromise.catch(() => { /* handled by awaiters */ });
  }
  try {
    await Promise.race([startPromise, _sleep(maxWaitMs)]);
  } catch (e) {
    startPromise = null;
    throw e;
  }
  if (await isServerAlive()) {
    return { alive: true, warming: false, elapsedMs: Date.now() - started };
  }
  return { alive: false, warming: true, elapsedMs: Date.now() - warmupStartedAt };
}

/**
 * Fire-and-forget engine warm — called at Next.js boot (instrumentation)
 * so the FIRST user request usually meets a ready engine instead of a
 * cold-start install. Safe to call repeatedly.
 */
export function startBackgroundWarm(): void {
  if (startPromise) return;
  const t0 = Date.now();
  console.log("[judge-engine] background warm-up starting …");
  ensureServer(300_000)
    .then((st) => {
      console.log(`[judge-engine] background warm-up done ` +
        `(alive=${st.alive}, ${((Date.now() - t0) / 1000).toFixed(1)}s)`);
    })
    .catch((e) => {
      console.error("[judge-engine] background warm-up FAILED:", e);
      startPromise = null;
    });
}
