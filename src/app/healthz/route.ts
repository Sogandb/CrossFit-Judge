export const dynamic = "force-dynamic";
/** Liveness for the web container (the engine has its own /api/health). */
export async function GET() {
  return Response.json({ ok: true, service: "crossfit-judge-web" });
}
