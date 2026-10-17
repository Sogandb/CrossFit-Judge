/**
 * Optional access protection for test deployments.
 * Set ACCESS_USER and ACCESS_PASSWORD to require HTTP Basic auth for the whole
 * site (UI + API). When unset, the app is open (e.g. behind a VPN / firewall).
 * /healthz stays public for load balancers and container health checks.
 */
import { NextRequest, NextResponse } from "next/server";

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };

export function proxy(req: NextRequest) {
  const user = process.env.ACCESS_USER;
  const pass = process.env.ACCESS_PASSWORD;
  if (!user || !pass) return NextResponse.next();
  if (req.nextUrl.pathname === "/healthz") return NextResponse.next();

  const header = req.headers.get("authorization") || "";
  if (header.startsWith("Basic ")) {
    try {
      const [u, ...rest] = atob(header.slice(6)).split(":");
      if (u === user && rest.join(":") === pass) return NextResponse.next();
    } catch { /* fall through */ }
  }
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="CrossFit Judge (test)"' },
  });
}
