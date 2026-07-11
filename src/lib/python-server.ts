/**
 * Manages the Python CrossFit Judge server as a child process of the
 * Next.js dev server.
 *
 * The server is started lazily on the first API request. If it crashes
 * (MediaPipe can segfault on certain inputs), it is automatically restarted
 * on the next request.
 */

import { spawn, type ChildProcess } from 'child_process';
import path from 'path';

const PYTHON_PORT = 8001;
const SERVICE_DIR = path.join(process.cwd(), 'mini-services', 'crossfit-judge');
const LD_PATH = [
  '/home/z/.agent-browser/browsers/chrome-150.0.7871.49',
  '/home/z/.venv/lib',
  process.env.LD_LIBRARY_PATH || '',
].join(':');

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

async function waitForServer(timeoutMs = 60000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isServerAlive()) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('Python server did not start within timeout');
}

function spawnServer(): ChildProcess {
  const env = {
    ...process.env,
    LD_LIBRARY_PATH: LD_PATH,
    MEDIAPIPE_DISABLE_GPU: '1',
    GLOG_minloglevel: '2',
    LIBGL_ALWAYS_SOFTWARE: '1',
    EGL_PLATFORM: 'surfaceless',
    HOME: '/home/z',
  };

  const proc = spawn('python3', ['main.py'], {
    cwd: SERVICE_DIR,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
  });

  proc.on('exit', (code, signal) => {
    console.error(`[python-server] exited code=${code} signal=${signal}`);
    pyProcess = null;
    startPromise = null;
  });

  proc.stdout?.on('data', (data: Buffer) => {
    const text = data.toString();
    if (!text.includes('absl::') && !text.includes('W0000') && !text.includes('ERR:')) {
      process.stderr.write(`[py] ${text}`);
    }
  });
  proc.stderr?.on('data', (data: Buffer) => {
    const text = data.toString();
    if (!text.includes('absl::') && !text.includes('W0000')) {
      process.stderr.write(`[py!] ${text}`);
    }
  });

  return proc;
}

export async function ensureServer(): Promise<void> {
  // Always check if the server is actually alive first, regardless of
  // pyProcess state (the process may have been killed externally or the
  // module may have been hot-reloaded losing state).
  if (await isServerAlive()) {
    return;
  }

  // Server is not alive. If pyProcess exists but is dead, clear it.
  if (pyProcess) {
    pyProcess = null;
  }

  // If another request is already starting the server, wait for it.
  if (startPromise) {
    return startPromise;
  }

  startPromise = (async () => {
    // Double-check in case another caller started the server while we waited.
    if (await isServerAlive()) return;

    pyProcess = spawnServer();
    await waitForServer();
  })();

  try {
    await startPromise;
  } catch (e) {
    // If startup failed, clear the promise so the next request can retry.
    startPromise = null;
    throw e;
  }
}
