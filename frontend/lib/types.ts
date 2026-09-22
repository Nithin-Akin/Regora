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
  }[];
  unmatched_files: string[];
  graph: GraphData;
  truncated: boolean;
  caveat: string;
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
};
export type AnswerStreamEvent =
  | { type: "status"; message: string }
  | { type: "delta"; text: string }
  | { type: "result"; answer: Answer }
  | { type: "error"; detail: string };
