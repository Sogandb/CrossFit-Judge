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

import { ensureServer } from '@/lib/python-server';
import http from 'node:http';
import { Readable } from 'node:stream';

const BACKEND_HOST = '127.0.0.1';
const BACKEND_PORT = 8001;

export const maxDuration = 300; // 5 minutes for large uploads + processing

async function proxy(
  req: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const pathStr = path.join('/');
  const url = new URL(req.url);
  const targetPath = `/api/${pathStr}?${url.searchParams.toString()}`;

  // Ensure the Python server is running before we pipe.
  try {
    await ensureServer();
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Server start failed';
    return Response.json({ error: msg }, { status: 503 });
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
      },
    );

    proxyReq.on('error', (err) => {
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
