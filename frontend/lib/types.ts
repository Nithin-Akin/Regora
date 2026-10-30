export type Node = {
  id: string;
  name: string;
  type: string;
  qualified_name: string;
  file_path: string;
  language: string;
  start_line: number;
  end_line: number;
  signature: string;
  source?: string;
  docstring: string;
  module: string;
  members?: string[];
  count?: number;
  score?: number;
  semantic_score?: number;
  mechanism?: string;
  snippet?: string;
};
export type Edge = {
  id: string;
  source: string;
  target: string;
  type: string;
  source_file?: string;
  source_line?: number;
  resolution?: string;
  confidence?: number;
  count?: number;
};
export type GraphData = {
  nodes: Node[];
  edges: Edge[];
  truncated?: boolean;
  total?: number;
};
export type Repository = {
  id: string;
  name: string;
  status: string;
  progress: number;
  message: string;
  created_at: string;
  fingerprint?: string;
  job_id: string;
  logs?: { status: string; message: string; elapsed_seconds: number }[];
  warnings?: string[];
  kind?: string;
  github_installation_id?: number;
};
export type GuardianRun = {
  id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETE" | "ERROR";
  pull_request?: number;
  pr_url?: string;
  head_sha?: string;
  command?: string;
  delivery_id?: string;
  retry_of?: string;
  created_at: string;
  updated_at?: string;
  started_at?: string;
  completed_at?: string;
  failed_at?: string;
  review_status?: string;
  policy_status?: string;
  comment_url?: string;
  error?: string;
};
export type GitHubIntegration = {
  status: "READY" | "NEEDS_SETUP";
  authentication: "GITHUB_APP" | "TOKEN_FALLBACK" | "MISSING";
  app_configured: boolean;
  webhook_configured: boolean;
  repository: {
    github_repository: boolean;
    bound: boolean;
    installation_id?: number;
  };
  webhook_path: string;
  setup_steps: string[];
  sync: {
    status: string;
    progress: number;
    message: string;
    error: string;
    indexed_sha: string;
    latest_github_sha: string;
    default_branch: string;
    last_synced_at: string;
    updated_at: string;
  };
  runs: GuardianRun[];
};
export type GraphVersion = {
  id: string;
  commit_sha: string;
  fingerprint: string;
  nodes: number;
  relationships: number;
  created_at: string;
  trigger: "index" | "push";
  format: string;
  current: boolean;
};
export type VersionHistory = {
  repository_id: string;
  indexed_sha: string;
  versions: GraphVersion[];
};
export type GraphDiffEvidence = {
  change: "added" | "removed" | "modified";
  id: string;
  name?: string;
  type: string;
  qualified_name?: string;
  file_path?: string;
  start_line?: number;
  end_line?: number;
  signature?: string;
  source_name?: string;
  target_name?: string;
  source_file?: string;
  source_line?: number;
  resolution?: string;
  changed_fields?: string[];
};
export type GraphDiff = {
  repository_id: string;
  base: GraphVersion;
  head: GraphVersion;
  summary: {
    symbols: { added: number; removed: number; modified: number };
    relationships: { added: number; removed: number; modified: number };
    affected_files: number;
    affected_modules: number;
    affected_endpoints: number;
    affected_database_entities: number;
  };
  risk: { score: number; level: "LOW" | "MEDIUM" | "HIGH" };
  affected: {
    files: string[];
    modules: string[];
    endpoints: string[];
    database_entities: string[];
  };
  symbols: GraphDiffEvidence[];
  relationships: GraphDiffEvidence[];
  truncated: boolean;
  limitations: string;
};
export type ArchitectureViolation = {
  rule_id: string;
  severity: "warning" | "error";
  message: string;
  path: string[];
  nodes: Pick<Node, "id" | "name" | "type" | "file_path" | "start_line" | "end_line">[];
  evidence: Edge[];
};
export type ArchitecturePolicy = {
  configured: boolean;
  source: string | null;
  status: "NOT_CONFIGURED" | "INVALID" | "PASS" | "WARN" | "FAIL";
  summary: {
    rules: number;
    passed: number;
    warnings: number;
    errors: number;
    violations: number;
  };
  rules: {
    id: string;
    name: string;
    type: "forbid_dependency" | "no_cycles";
    severity: "warning" | "error";
    status: "PASS" | "WARN" | "FAIL";
    violation_count: number;
    violations: ArchitectureViolation[];
  }[];
  violations: ArchitectureViolation[];
  error: string | null;
};
export type Overview = {
  files: number;
  lines: number;
  nodes: number;
  relationships: number;
  counts: Record<string, number>;
  languages: Record<string, number>;
  largest_modules: Record<string, number>;
  hubs: { node: Node; degree: number }[];
  cycles: string[][];
  potentially_unused: string[];
  unresolved_relationships: number;
  warnings?: string[];
  architecture?: Answer;
  architecture_policy?: ArchitecturePolicy;
};
export type Impact = {
  symbol_id: string;
  score: number;
  risk: string;
  features: Record<string, number>;
  direct_callers: string[];
  indirect_callers: string[];
  affected_files: string[];
  affected_modules: string[];
  affected_endpoints: string[];
  database_interactions: string[];
  dependency_depth: number;
  blast_radius: number;
  paths: string[][];
  graph: GraphData;
  caveat: string;
};
export type RefactoringPlanStage = {
  title: string;
  objective: string;
  actions: string[];
  evidence_ids: string[];
  verification: string[];
};
export type RefactoringPlan = {
  target: Node;
  goal: string;
  summary: string;
  confidence: number;
  grounding: "llm-with-evidence" | "static-evidence";
  warning?: string | null;
  impact: {
    score: number;
    risk: "LOW" | "MEDIUM" | "HIGH";
    blast_radius: number;
    dependency_depth: number;
    affected_files: string[];
    affected_modules: string[];
    affected_endpoints: string[];
    database_interactions: string[];
    paths: string[][];
    caveat: string;
  };
  related_tests: string[];
  missing_test_signal: boolean;
  stages: RefactoringPlanStage[];
  citations: Node[];
  graph: GraphData;
};
export type PullRequestImpact = {
  pull_request: {
    number: number;
    title: string;
    url: string;
    state: string;
    base: string;
    head: string;
  };
  summary: {
    files_changed: number;
    symbols_changed: number;
    affected_files: number;
    affected_endpoints: number;
    score: number;
    risk: string;
  };
  files: {
    path: string;
    status: string;
    additions: number;
    deletions: number;
    symbols: Node[];
  }[];
  impacts: {
    node: Node;
    score: number;
    risk: string;
    blast_radius: number;
    affected_files: string[];
    affected_endpoints: string[];
    dependency_depth: number;
    related_tests: string[];
  }[];
  review: {
    status: "ATTENTION" | "REVIEW";
    headline: string;
    summary: string;
    related_tests: string[];
    changed_test_files: string[];
    coverage_gaps: {
      symbol_id: string;
      symbol: string;
      file: string;
      start_line: number;
      end_line: number;
      risk: string;
      reason: string;
    }[];
    findings: {
      id: string;
      severity: string;
      title: string;
      detail: string;
      symbol_id: string;
      file: string;
      start_line: number;
      end_line: number;
      related_tests: string[];
    }[];
    checklist: {
      id: string;
      label: string;
      status: "pass" | "warning";
      detail: string;
    }[];
    grounding: "static-evidence";
  };
  unmatched_files: string[];
  graph: GraphData;
  truncated: boolean;
  caveat: string;
};
export type PullRequestReviewPublication = {
  id: number;
  url: string;
  created_at: string;
  action: "created" | "updated";
};
export type Citation = {
  symbol_id: string;
  file: string;
  start_line: number;
  end_line: number;
};
export type Answer = {
  answer: string;
  confidence: number;
  symbols: string[];
  paths: string[][];
  citations: Citation[];
  grounding: string;
  intent: string;
  session_id: string;
  warning?: string;
  tool_calls: { name: string; arguments: Record<string, unknown> }[];
};
export type Message = {
  role: "user" | "assistant";
  content: string;
  result?: Answer;
  streaming?: boolean;
  retryText?: string;
};
export type AnswerStreamEvent =
  | { type: "status"; message: string }
  | { type: "delta"; text: string }
  | { type: "result"; answer: Answer }
  | { type: "error"; detail: string };
