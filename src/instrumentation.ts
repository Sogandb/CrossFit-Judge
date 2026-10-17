/**
 * Next.js server startup hook.
 *
 * Proactively warms the CrossFit Judge Python engine at server boot instead
 * of lazily on the first API request. After sandbox resets the self-healing
 * dependency reinstall takes 40-120 s; without this, the FIRST user upload
 * hits that cold start (and preview tunnels kill long-blocked requests —
 * the user sees a frozen 1 % upload bar). With the background warm, users
 * normally meet a ready engine, and even mid-warmup requests get a fast
 * 503 {warming_up:true} that the client retries politely.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  try {
    const { startBackgroundWarm } = await import("@/lib/python-server");
    startBackgroundWarm();
  } catch (e) {
    console.error("[instrumentation] engine warm-up could not start:", e);
  }
}
