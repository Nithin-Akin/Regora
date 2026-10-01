import { auth } from "@/auth";
import { signedIdentityHeaders, type GatewayIdentity } from "@/lib/backend-auth";

export const dynamic = "force-dynamic";
export const maxDuration = 900;

const HOP_BY_HOP = new Set([
  "connection",
  "content-length",
  "content-encoding",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

async function identity(): Promise<GatewayIdentity | null> {
  if (process.env.AUTH_MODE !== "github") return { id: "local" };
  const session = await auth();
  if (!session?.user?.id) return null;
  return {
    id: session.user.id,
    githubAccessToken: session.githubAccessToken,
  };
}

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const user = await identity();
  if (!user) return Response.json({ detail: "Sign in with GitHub to continue" }, { status: 401 });

  const { path } = await context.params;
  const incoming = new URL(request.url);
  const backend = new URL(
    `/api/${path.map(encodeURIComponent).join("/")}${incoming.search}`,
    process.env.BACKEND_URL || "http://localhost:8000",
  );
  const headers = new Headers();
  for (const name of ["accept", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  for (const [name, value] of Object.entries(signedIdentityHeaders(user))) {
    headers.set(name, value);
  }

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };
  if (!new Set(["GET", "HEAD"]).has(request.method)) {
    init.body = request.body;
    init.duplex = "half";
  }
  try {
    const response = await fetch(backend, init);
    const responseHeaders = new Headers();
    response.headers.forEach((value, name) => {
      if (!HOP_BY_HOP.has(name.toLowerCase())) responseHeaders.set(name, value);
    });
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { detail: "The Regora backend is unavailable" },
      { status: 502 },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
export const HEAD = forward;
