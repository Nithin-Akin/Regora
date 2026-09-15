import { describe, it, expect, vi, afterEach } from "vitest";
import { mergeGraph, api } from "../lib/api";
import type { Node, Edge } from "../lib/types";
const node = (id: string) => ({ id, name: id, type: "Function" }) as Node;
describe("graph expansion", () => {
  it("merges neighborhoods without duplicate nodes or edges", () => {
    const e = { id: "e", source: "a", target: "b", type: "CALLS" } as Edge;
    const result = mergeGraph(
      { nodes: [node("a"), node("b")], edges: [e] },
      { nodes: [node("b"), node("c")], edges: [e] },
    );
    expect(result.nodes.map((n) => n.id)).toEqual(["a", "b", "c"]);
    expect(result.edges).toHaveLength(1);
  });
  it("preserves a truncated response indicator", () => {
    expect(
      mergeGraph(
        { nodes: [], edges: [], truncated: true },
        { nodes: [], edges: [] },
      ).truncated,
    ).toBe(true);
  });
});
describe("API errors", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("surfaces useful server errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: "Neo4j unavailable" }), {
            status: 503,
          }),
        ),
    );
    await expect(api("/health")).rejects.toThrow("Neo4j unavailable");
  });
  it("handles successful deletion without parsing an empty body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    await expect(
      api("/repositories/r", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });
});
