import { afterEach, describe, expect, it } from "vitest";
import { createHash, createHmac } from "node:crypto";
import { signedIdentityHeaders } from "../lib/backend-auth";

const originalMode = process.env.AUTH_MODE;
const originalSecret = process.env.AUTH_SHARED_SECRET;

afterEach(() => {
  process.env.AUTH_MODE = originalMode;
  process.env.AUTH_SHARED_SECRET = originalSecret;
});

describe("backend gateway authentication", () => {
  it("signs a GitHub identity for the backend", () => {
    process.env.AUTH_MODE = "github";
    process.env.AUTH_SHARED_SECRET = "a-secure-shared-secret-with-32-characters";
    const result = signedIdentityHeaders(
      { id: "github:42", githubAccessToken: "github-token" },
      "1000",
    );
    const tokenHash = createHash("sha256").update("github-token").digest("hex");
    const expected = createHmac("sha256", process.env.AUTH_SHARED_SECRET)
      .update(`v1:1000:github:42:${tokenHash}`)
      .digest("hex");
    expect(result["x-regora-auth-signature"]).toBe(expected);
    expect(result["x-regora-github-token"]).toBe("github-token");
  });

  it("requires a strong shared secret in GitHub mode", () => {
    process.env.AUTH_MODE = "github";
    process.env.AUTH_SHARED_SECRET = "short";
    expect(() => signedIdentityHeaders({ id: "github:42" }, "1000")).toThrow(
      "at least 32 characters",
    );
  });
});
