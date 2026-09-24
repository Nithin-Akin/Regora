import { describe, expect, it } from "vitest";

import {
  buildPullRequestImpactMarkdown,
  pullRequestReportFilename,
} from "../lib/pr-report";
import type { PullRequestImpact } from "../lib/types";

const report = {
  pull_request: {
    number: 42,
    title: "Change auth | validation",
    url: "https://github.com/acme/shop/pull/42",
    state: "open",
    base: "main",
    head: "auth-change",
  },
  summary: {
    files_changed: 2,
    symbols_changed: 1,
    affected_files: 4,
    affected_endpoints: 2,
    score: 47,
    risk: "MEDIUM",
  },
  files: [
    {
      path: "services/auth.py",
      status: "modified",
      additions: 8,
      deletions: 3,
      symbols: [],
    },
  ],
  impacts: [
    {
      node: {
        id: "verify",
        name: "verify_token",
        type: "Function",
        qualified_name: "services.auth.verify_token",
        file_path: "services/auth.py",
        language: "Python",
        start_line: 8,
        end_line: 14,
        signature: "",
        docstring: "",
        module: "services",
      },
      score: 47,
      risk: "MEDIUM",
      blast_radius: 7,
      affected_files: ["services/auth.py", "api/routes.py"],
      affected_endpoints: ["POST /checkout"],
      dependency_depth: 3,
    },
  ],
  unmatched_files: ["README.md"],
  graph: { nodes: [], edges: [] },
  truncated: false,
  caveat: "Potential impact is based on static dependencies.",
} satisfies PullRequestImpact;

describe("pull request impact report", () => {
  it("creates a deterministic Markdown report with review-ready evidence", () => {
    const markdown = buildPullRequestImpactMarkdown(report);
    expect(markdown).toContain("PR #42: Change auth \\| validation");
    expect(markdown).toContain("**Highest risk: MEDIUM (47/100)**");
    expect(markdown).toContain("`verify_token`");
    expect(markdown).toContain("| 47 | 7 | 2 | 1 |");
    expect(markdown).toContain("- `README.md`");
    expect(markdown).toContain(report.caveat);
  });

  it("uses a stable filename containing the pull request number", () => {
    expect(pullRequestReportFilename(report)).toBe("regora-pr-42-impact.md");
  });
});
