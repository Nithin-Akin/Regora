export async function GET() {
  return Response.json({ authMode: process.env.AUTH_MODE || "local" });
}
