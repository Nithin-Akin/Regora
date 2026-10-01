import { createHash, createHmac } from "node:crypto";

export type GatewayIdentity = {
  id: string;
  githubAccessToken?: string;
};

export function signedIdentityHeaders(
  identity: GatewayIdentity,
  timestamp = Math.floor(Date.now() / 1000).toString(),
) {
  const token = identity.githubAccessToken || "";
  const headers: Record<string, string> = {
    "x-regora-user-id": identity.id,
    "x-regora-auth-timestamp": timestamp,
  };
  if (token) headers["x-regora-github-token"] = token;
  if (process.env.AUTH_MODE === "github") {
    const secret = process.env.AUTH_SHARED_SECRET || "";
    if (secret.length < 32) {
      throw new Error("AUTH_SHARED_SECRET must contain at least 32 characters");
    }
    const tokenHash = createHash("sha256").update(token).digest("hex");
    headers["x-regora-auth-signature"] = createHmac("sha256", secret)
      .update(`v1:${timestamp}:${identity.id}:${tokenHash}`)
      .digest("hex");
  }
  return headers;
}
