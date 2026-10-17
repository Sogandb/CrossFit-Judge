/**
 * Unified proxy route — handles ALL requests to the Python backend.
 *
 * Uses Node's http module for zero-memory streaming. This is critical for
 * large video uploads: the request body is piped directly to Python without
 * buffering in the Next.js process, preventing OOM kills.
 *
 * All frontend requests go through /api/judge/* — no more separate upload
 * route or direct gateway URLs. This is simpler and more robust.
 */

import { ensureServer, ENGINE_HOST, ENGINE_PORT } from '@/lib/python-server';
import http from 'node:http';
import { appendFile } from 'node:fs/promises';
import { Readable } from 'node:stream';

const BACKEND_HOST = ENGINE_HOST;
const BACKEND_PORT = ENGINE_PORT;
// Optional file access log (empty = disabled; container logs are enough).
const ACCESS_LOG = process.env.JUDGE_PROXY_ACCESS_LOG || '';

export const maxDuration = 3600; // long enough for large video uploads

/**
 * Timestamped access log — one line per request, evidence forever.
 * Diagnoses "did the phone's request ever reach us?" instantly after any
 * user report (the Oct-8 tunnel death took hours to forensicate without it).
 * Fire-and-forget: logging must never block or break a streaming upload.
 */
function logAccess(
  method: string,
  path: string,
  status: number,
  ms: number,
  reqLen: number | null,
  ua: string,
): void {
  const line = `${new Date().toISOString()} ${method} /${path} ${status} ${ms}ms ` +
    `req=${reqLen ?? '-'}B ua="${ua.slice(0, 160)}"\n`;
  if (!ACCESS_LOG) return;
  appendFile(ACCESS_LOG, line, 'utf-8').catch(() => {/* logging is best-effort */});
}

/**
 * Liveness cache — chunked uploads fire MANY small requests (adaptive
 * chunking); running a health-check + potential dep-verification per
 * request adds avoidable latency to every chunk. A recent-positive check
 * is trusted for a short TTL, and any backend connection error
 * invalidates it immediately.
 */
let lastAliveAt = 0;
const ALIVE_TTL_MS = 15_000;

async function proxy(
  req: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const t0 = Date.now();
  const { path } = await context.params;
  const pathStr = path.join('/');
  const url = new URL(req.url);
  const targetPath = `/api/${pathStr}?${url.searchParams.toString()}`;
  const ua = req.headers.get('user-agent') || '';
  const reqLen = Number(req.headers.get('content-length')) || null;
  const log = (status: number) =>
    logAccess(req.method, pathStr, status, Date.now() - t0, reqLen, ua);

  // Ensure the Python server is running before we pipe (TTL-cached).
  // BOUNDED wait: after a sandbox reset the self-healing reinstall takes
  // 40-120 s — a request that blocks on that dies inside the preview tunnel
  // (the user sees a frozen upload bar). Instead we answer 503 warming_up
  // FAST and let the client retry politely until the engine is ready.
  if (Date.now() - lastAliveAt > ALIVE_TTL_MS) {
    try {
      const st = await ensureServer(20_000);
      if (st.alive) {
        lastAliveAt = Date.now();
      } else {
        // warmup still running (deps reinstall / spawn)
        log(503);
        return Response.json(
          {
            error: "Analysis engine is starting up — please retry",
            warming_up: true,
            retry_after_sec: 5,
          },
          { status: 503, headers: { "Retry-After": "5" } },
        );
      }
    } catch (e: unknown) {
      lastAliveAt = 0;
      const msg = e instanceof Error ? e.message : 'Server start failed';
      log(503);
      return Response.json({ error: msg }, { status: 503 });
    }
  }

  // Convert the web ReadableStream to a Node readable stream for piping.
  const nodeBody = req.body ? toNodeReadable(req.body) : null;

  // Forward all headers except host (Node http sets it automatically).
  const headers: Record<string, string> = {};
  req.headers.forEach((value, key) => {
    if (key.toLowerCase() === 'host') return;
    headers[key] = value;
  });

  return new Promise<Response>((resolve) => {
    const proxyReq = http.request(
      {
        hostname: BACKEND_HOST,
        port: BACKEND_PORT,
        path: targetPath,
        method: req.method,
        headers,
      },
      (proxyRes) => {
        const respHeaders = new Headers();
        for (const [k, v] of Object.entries(proxyRes.headers)) {
          if (v) respHeaders.set(k, Array.isArray(v) ? v.join(', ') : v);
        }

        // Stream the response body back to the client.
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            proxyRes.on('data', (chunk: Buffer) => {
              controller.enqueue(new Uint8Array(chunk));
            });
            proxyRes.on('end', () => controller.close());
            proxyRes.on('error', (err) => controller.error(err));
          },
          cancel() {
            proxyRes.destroy();
          },
        });

        resolve(
          new Response(stream, {
            status: proxyRes.statusCode || 200,
            headers: respHeaders,
          }),
        );
        log(proxyRes.statusCode || 200);
      },
    );

    proxyReq.on('error', (err) => {
      lastAliveAt = 0; // backend unreachable → re-ensure on the next request
      log(502);
      resolve(
        Response.json(
          { error: `Proxy error: ${err.message}` },
          { status: 502 },
        ),
      );
    });

    // Pipe the request body to the backend (zero-memory streaming).
    if (nodeBody) {
      nodeBody.pipe(proxyReq);
    } else {
      proxyReq.end();
    }
  });
}

/**
 * Convert a Web ReadableStream to a Node.js readable stream.
 */
function toNodeReadable(webStream: ReadableStream<Uint8Array>) {
  const reader = webStream.getReader();
  return new Readable({
    async read() {
      try {
        const { done, value } = await reader.read();
        if (done) {
          this.push(null);
        } else {
          this.push(Buffer.from(value));
        }
      } catch (err) {
        this.destroy(err as Error);
      }
    },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
