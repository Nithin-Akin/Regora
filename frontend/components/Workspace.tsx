"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  ArrowRight,
  BookOpen,
  ChevronRight,
  Code2,
  Database,
  FileCode2,
  Folder,
  GitBranch,
  Layers,
  LoaderCircle,
  MessageSquare,
  Network,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  X,
  Expand,
  PanelLeftClose,
  PanelRightClose,
  Check,
  AlertTriangle,
} from "lucide-react";
import Brand from "./Brand";
import SourceViewer from "./SourceViewer";
import { api, mergeGraph } from "@/lib/api";
import type {
  Node,
  GraphData,
  Repository,
  Overview,
  Impact,
  Citation,
  Answer,
  Message,
  Edge,
} from "@/lib/types";
const Graph = dynamic(() => import("./Graph"), {
  ssr: false,
  loading: () => (
    <div className="empty">
      <LoaderCircle className="spin" />
      Preparing graph…
    </div>
  ),
});
const emptyGraph: GraphData = { nodes: [], edges: [] };
const stages = [
  "QUEUED",
  "CLONING",
  "SCANNING",
  "PARSING",
  "BUILDING_GRAPH",
  "EMBEDDING",
  "ANALYZING",
  "READY",
];
const labels = [
  "Queued",
  "Get repository",
  "Scan & detect languages",
  "Parse & extract symbols",
  "Resolve & build graph",
  "Generate embeddings",
  "Analyze architecture",
  "Ready",
];

export default function Workspace({
  id,
  initialImpact,
}: {
  id: string;
  initialImpact?: string;
}) {
  const base = "/repositories/" + id;
  const [repo, setRepo] = useState<Repository | null>(null);
  const [error, setError] = useState("");
  const [graph, setGraph] = useState<GraphData>(emptyGraph);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [files, setFiles] = useState<Node[]>([]);
  const [selected, setSelected] = useState<Node | null>(null);
  const [edges, setEdges] = useState<{ incoming: Edge[]; outgoing: Edge[] }>({
    incoming: [],
    outgoing: [],
  });
  const [view, setView] = useState<"architecture" | "symbols" | "overview">(
    "architecture",
  );
  const [right, setRight] = useState<"assistant" | "inspect" | "impact">(
    "assistant",
  );
  const [layout, setLayout] = useState("cose");
  const [depth, setDepth] = useState(1);
  const [nodeType, setNodeType] = useState("");
  const [relationship, setRelationship] = useState("");
  const [highlights, setHighlights] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState("hybrid");
  const [results, setResults] = useState<Node[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchWarning, setSearchWarning] = useState("");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [asking, setAsking] = useState(false);
  const [session, setSession] = useState("");
  const [citation, setCitation] = useState<Citation | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [working, setWorking] = useState("");
  const [pathStart, setPathStart] = useState<Node | null>(null);
  const [pathNotice, setPathNotice] = useState("");
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const fail = useCallback(
    (e: unknown) => setError((e as Error).message || "Something went wrong"),
    [],
  );
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    async function poll() {
      try {
        const data = await api<Repository>(base + "/status");
        if (stopped) return;
        setRepo(data);
        if (!["READY", "FAILED"].includes(data.status))
          timer = setTimeout(poll, 2000);
      } catch (e) {
        if (!stopped) {
          fail(e);
          timer = setTimeout(poll, 5000);
        }
      }
    }
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [base, fail]);
  useEffect(() => {
    if (repo?.status !== "READY") return;
    let cancelled = false;
    Promise.all([
      api<GraphData>(base + "/graph"),
      api<Overview>(base + "/overview"),
      api<Node[]>(base + "/files"),
    ])
      .then(([g, o, f]) => {
        if (!cancelled) {
          setGraph(g);
          setOverview(o);
          setFiles(f);
        }
      })
      .catch(fail);
    const stored = localStorage.getItem("repograph-session-" + id);
    if (stored) {
      setSession(stored);
      api<{ messages: { role: "user" | "assistant"; content: string }[] }>(
        base + "/chat/" + stored,
      )
        .then((s) => {
          if (!cancelled) setMessages(s.messages);
        })
        .catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  }, [base, id, repo?.status, fail]);
  const selectNode = useCallback(
    async (n: Node) => {
      setError("");
      setPathNotice("");
      if (n.type === "Component") {
        setWorking("Opening component");
        try {
          const g = await api<GraphData>(
            base +
              "/graph?view=symbols&limit=500&module=" +
              encodeURIComponent(n.name),
          );
          setGraph(g);
          setView("symbols");
          setNodeType("");
          setRelationship("");
          setSelected(null);
          setHighlights([]);
        } catch (e) {
          fail(e);
        } finally {
          setWorking("");
        }
        return;
      }
      setSelected(n);
      setView("symbols");
      setNodeType("");
      setRight("inspect");
      setRightOpen(true);
      setHighlights([]);
      try {
        const result = await api<{
          node: Node;
          incoming: Edge[];
          outgoing: Edge[];
          neighbors: GraphData;
        }>(base + "/symbols/" + n.id);
        setSelected(result.node);
        setEdges(result);
        setGraph((current) =>
          current.nodes.some((x) => x.type === "Component")
            ? result.neighbors
            : current.nodes.some((x) => x.id === n.id)
              ? current
              : mergeGraph(current, result.neighbors),
        );
      } catch (e) {
        fail(e);
      }
    },
    [base, fail],
  );
  async function loadView(next: "architecture" | "symbols" | "overview") {
    setView(next);
    setNodeType("");
    setRelationship("");
    setHighlights([]);
    setSelected(null);
    if (next === "overview") {
      try {
        setOverview(await api<Overview>(base + "/overview"));
      } catch (e) {
        fail(e);
      }
      return;
    }
    setWorking("Loading graph");
    try {
      setGraph(await api<GraphData>(base + "/graph?view=" + next));
    } catch (e) {
      fail(e);
    } finally {
      setWorking("");
    }
  }
  async function expand(direction = "both", relations = "") {
    if (!selected) return;
    setWorking("Exploring dependencies");
    try {
      const g = await api<GraphData>(
        `${base}/symbols/${selected.id}/neighbors?depth=${depth}&direction=${direction}&relationships=${relations}`,
      );
      setGraph(g);
      setView("symbols");
      setHighlights([]);
    } catch (e) {
      fail(e);
    } finally {
      setWorking("");
    }
  }
  async function analyzeImpact(symbolId = selected?.id) {
    if (!symbolId) return;
    setWorking("Calculating impact");
    try {
      const result = await api<Impact>(`${base}/symbols/${symbolId}/impact`);
      setImpact(result);
      setLayout("dagre");
      setRight("impact");
      setRightOpen(true);
      setGraph(result.graph);
      setHighlights(result.graph.nodes.map((n) => n.id));
      setView("symbols");
    } catch (e) {
      fail(e);
    } finally {
      setWorking("");
    }
  }
  useEffect(() => {
    if (initialImpact && repo?.status === "READY")
      void analyzeImpact(initialImpact);
  }, [initialImpact, repo?.status]); // eslint-disable-line
  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setSearchWarning("");
    try {
      const result = await api<{ results: Node[]; warning?: string }>(
        `${base}/search?q=${encodeURIComponent(query)}&mode=${searchMode}`,
      );
      setResults(result.results);
      setSearchWarning(result.warning || "");
    } catch (e) {
      fail(e);
    } finally {
      setSearching(false);
    }
  }
  async function showEvidence(answer: Answer) {
    const ids = [...new Set([...answer.symbols, ...answer.paths.flat()])];
    const chunks = await Promise.all(
      ids
        .slice(0, 12)
        .map((symbol) =>
          api<GraphData>(`${base}/symbols/${symbol}/neighbors?depth=1`),
        ),
    );
    setGraph(chunks.reduce(mergeGraph, emptyGraph));
    setHighlights(ids);
    setLayout("dagre");
    setView("symbols");
  }
  async function ask(text = question) {
    if (!text.trim() || asking) return;
    setQuestion("");
    setRight("assistant");
    setRightOpen(true);
    setMessages((m) => [...m, { role: "user", content: text }]);
    setAsking(true);
    setError("");
    try {
      const result = await api<Answer>(base + "/ask", {
        method: "POST",
        body: JSON.stringify({
          question: text,
          session_id: session || null,
          symbol_id: selected?.id || null,
        }),
      });
      setSession(result.session_id);
      localStorage.setItem("repograph-session-" + id, result.session_id);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: result.answer, result },
      ]);
      await showEvidence(result);
    } catch (e) {
      fail(e);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: "The request failed. " + (e as Error).message,
        },
      ]);
    } finally {
      setAsking(false);
    }
  }
  async function trace() {
    if (!selected) return;
    setWorking("Tracing dependencies");
    try {
      if (pathStart) {
        const result = await api<{ path: string[]; graph: GraphData }>(
          `${base}/paths?source_id=${pathStart.id}&target_id=${selected.id}`,
        );
        if (!result.path.length) {
          setPathNotice("No directed static dependency path was found.");
          return;
        }
        setGraph(result.graph);
        setHighlights(result.path);
        setPathStart(null);
      } else {
        const result = await api<{ paths: string[][]; graph: GraphData }>(
          base + "/trace",
          { method: "POST", body: JSON.stringify({ source_id: selected.id }) },
        );
        setGraph(result.graph);
        setHighlights(result.paths.flat());
        if (!result.paths.length)
          setPathNotice("No resolved downstream path was found.");
      }
      setView("symbols");
    } catch (e) {
      fail(e);
    } finally {
      setWorking("");
    }
  }
  async function retry() {
    setWorking("Reindexing");
    try {
      await api(base + "/reindex", { method: "POST" });
      location.reload();
    } catch (e) {
      fail(e);
    } finally {
      setWorking("");
    }
  }
  const filteredGraph = useMemo(() => {
    const nodes = graph.nodes.filter((n) => !nodeType || n.type === nodeType);
    const ids = new Set(nodes.map((n) => n.id));
    return {
      ...graph,
      nodes,
      edges: graph.edges.filter(
        (e) =>
          ids.has(e.source) &&
          ids.has(e.target) &&
          (!relationship || e.type === relationship),
      ),
    };
  }, [graph, nodeType, relationship]);
  const groups = useMemo(() => {
    const map = new Map<string, Node[]>();
    files.forEach((f) => {
      const group = f.module || "root";
      map.set(group, [...(map.get(group) || []), f]);
    });
    return [...map.entries()];
  }, [files]);
  const openSource = (node: Node) =>
    setCitation({
      symbol_id: node.id,
      file: node.file_path,
      start_line: node.start_line,
      end_line: node.end_line,
    });
  if (!repo || repo.status !== "READY")
    return (
      <>
        <header className="topbar">
          <Brand />
          <Link href="/repositories">
            Repositories <ArrowRight size={16} />
          </Link>
        </header>
        <main className="progress-page">
          <div className="eyebrow">REPOSITORY INGESTION</div>
          <h1>
            {repo?.status === "FAILED"
              ? "Analysis needs attention"
              : repo
                ? "Mapping " + repo.name
                : "Connecting to your workspace"}
          </h1>
          <p className="muted">
            {repo?.message || "Waiting for the repository service…"}
          </p>
          {error && <div className="error">{error}</div>}
          {repo && (
            <>
              <div className="progress-track">
                <i style={{ width: repo.progress + "%" }} />
              </div>
              <div className="progress-label">
                <span>{repo.status}</span>
                <strong>{repo.progress}%</strong>
              </div>
              <ol className="ingestion-stages">
                {stages.map((s, index) => {
                  const current = stages.indexOf(repo.status);
                  return (
                    <li
                      key={s}
                      className={
                        index < current
                          ? "done"
                          : index === current
                            ? "current"
                            : ""
                      }
                    >
                      {index < current ? (
                        <Check size={16} />
                      ) : index === current ? (
                        <LoaderCircle className="spin" size={16} />
                      ) : (
                        <span className="stage-number">{index + 1}</span>
                      )}
                      {labels[index]}
                    </li>
                  );
                })}
              </ol>
              {repo.status === "FAILED" && (
                <button
                  className="button primary"
                  onClick={() => void retry()}
                  disabled={!!working}
                >
                  <RefreshCw size={16} />
                  Retry analysis
                </button>
              )}
              <details className="job-logs">
                <summary>Processing log</summary>
                {repo.logs?.map((l, index) => (
                  <p key={index}>
                    <span>{l.elapsed_seconds}s</span>
                    {l.message}
                  </p>
                ))}
              </details>
              <p className="hint">
                This job runs in the background. You can leave this page and
                return later.
              </p>
            </>
          )}
        </main>
      </>
    );
  return (
    <div className="workspace">
      <header className="workspace-header">
        <Brand />
        <span className="header-divider" />
        <Link href="/repositories" className="muted">
          Repositories
        </Link>
        <ChevronRight size={14} />
        <strong>{repo.name}</strong>
        <span className="indexed">
          <Check size={12} />
          Indexed
        </span>
        <div className="header-end">
          <span className="fingerprint">{repo.fingerprint?.slice(0, 8)}</span>
          <button
            className="icon-button"
            title="Reindex repository"
            disabled={!!working}
            onClick={() => void retry()}
          >
            <RefreshCw size={16} />
          </button>
          <Link href="/" className="button subtle small">
            New repository <PlusIcon />
          </Link>
        </div>
      </header>
      {error && (
        <div className="workspace-error error" role="alert">
          {error}
          <button
            className="icon-button"
            onClick={() => setError("")}
            aria-label="Dismiss error"
          >
            <X size={15} />
          </button>
        </div>
      )}
      <div
        className={
          "workspace-grid " +
          (!leftOpen ? "hide-left " : "") +
          (!rightOpen ? "hide-right" : "")
        }
      >
        <aside className="sidebar">
          <div className="sidebar-heading">
            <span>EXPLORER</span>
            <button
              className="icon-button"
              title="Hide explorer"
              onClick={() => setLeftOpen(false)}
            >
              <PanelLeftClose size={15} />
            </button>
          </div>
          <form onSubmit={search} className="repo-search">
            <div className="input-icon">
              <Search size={15} />
              <input
                aria-label="Search repository"
                placeholder="Search your code…"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  if (!e.target.value) setResults(null);
                }}
              />
              <button
                className="icon-button"
                title="Run search"
                disabled={searching}
              >
                {searching ? (
                  <LoaderCircle className="spin" size={14} />
                ) : (
                  <ArrowRight size={14} />
                )}
              </button>
            </div>
            <select
              aria-label="Search mode"
              value={searchMode}
              onChange={(e) => setSearchMode(e.target.value)}
            >
              <option value="hybrid">Hybrid search</option>
              <option value="symbol">Symbol search</option>
              <option value="text">Text search</option>
              <option value="semantic">Semantic search</option>
            </select>
          </form>
          {results !== null ? (
            <div className="search-results">
              <div className="section-label">
                {results.length} RESULTS
                <button
                  className="icon-button"
                  title="Clear search"
                  onClick={() => setResults(null)}
                >
                  <X size={13} />
                </button>
              </div>
              {searchWarning && <p className="hint warning">{searchWarning}</p>}
              {results.map((n) => (
                <button
                  className="search-result"
                  key={n.id}
                  onClick={() => void selectNode(n)}
                >
                  <strong>{n.name}</strong>
                  <span>
                    {n.file_path}:{n.start_line}–{n.end_line}
                  </span>
                  <small>
                    {n.mechanism} · {n.score?.toFixed(3)}
                  </small>
                  <code>{n.snippet?.slice(0, 100)}</code>
                </button>
              ))}
              {results.length === 0 && (
                <p className="hint">
                  No matches. Try a symbol name or different search mode.
                </p>
              )}
            </div>
          ) : (
            <div className="file-tree">
              <div className="section-label">
                SOURCE FILES <span>{files.length}</span>
              </div>
              {groups.map(([group, items]) => (
                <details key={group} open>
                  <summary>
                    <Folder size={14} />
                    {group}
                    <span>{items.length}</span>
                  </summary>
                  {items.map((f) => (
                    <button
                      className={selected?.id === f.id ? "selected" : ""}
                      key={f.id}
                      onClick={() => void selectNode(f)}
                      title={f.file_path}
                    >
                      <FileCode2 size={14} />
                      {f.name}
                    </button>
                  ))}
                </details>
              ))}
            </div>
          )}
          <div className="sidebar-bottom">
            <div className="section-label">REPOSITORY HEALTH</div>
            <div className="mini-stat">
              <span>Source files</span>
              <strong>{overview?.files}</strong>
            </div>
            <div className="mini-stat">
              <span>Lines analyzed</span>
              <strong>{overview?.lines.toLocaleString()}</strong>
            </div>
            <div className="mini-stat">
              <span>API endpoints</span>
              <strong>{overview?.counts.Endpoint || 0}</strong>
            </div>
            {overview && overview.cycles.length > 0 && (
              <button
                className="cycle-alert"
                onClick={() => {
                  setView("overview");
                }}
              >
                <AlertTriangle size={14} />
                {overview.cycles.length} dependency cycle
                {overview.cycles.length > 1 ? "s" : ""}
                <ChevronRight size={14} />
              </button>
            )}
            <div className="language-bar">
              {Object.entries(overview?.languages || {}).map(
                ([name, count]) => (
                  <i
                    key={name}
                    title={`${name}: ${count} files`}
                    style={{
                      width: (count / (overview?.files || 1)) * 100 + "%",
                      background:
                        name === "Python"
                          ? "#b6a0f5"
                          : name === "TypeScript"
                            ? "#66b9dc"
                            : "#dec16b",
                    }}
                  />
                ),
              )}
            </div>
            <p className="hint">
              {Object.keys(overview?.languages || {}).join(" · ")}
            </p>
          </div>
        </aside>
        <section className="center-panel">
          <div className="workspace-tabs">
            {!leftOpen && (
              <button
                className="icon-button"
                title="Show explorer"
                onClick={() => setLeftOpen(true)}
              >
                <Folder size={16} />
              </button>
            )}
            <button
              className={view === "architecture" ? "active" : ""}
              onClick={() => void loadView("architecture")}
            >
              <Layers size={15} />
              Architecture
            </button>
            <button
              className={view === "symbols" ? "active" : ""}
              onClick={() => void loadView("symbols")}
            >
              <Network size={15} />
              Dependencies
            </button>
            <button
              className={view === "overview" ? "active" : ""}
              onClick={() => void loadView("overview")}
            >
              <Activity size={15} />
              Overview
            </button>
            <div className="grow" />
            <button
              className="icon-button"
              title="Expand graph workspace"
              onClick={() => {
                setLeftOpen(false);
                setRightOpen(false);
              }}
            >
              <Expand size={15} />
            </button>
            {!rightOpen && (
              <button
                className="icon-button"
                title="Show assistant"
                onClick={() => setRightOpen(true)}
              >
                <MessageSquare size={16} />
              </button>
            )}
          </div>
          {view !== "overview" ? (
            <>
              <div className="graph-toolbar">
                <span className="view-label">
                  {view === "architecture" ? "Component map" : "Symbol graph"}
                </span>
                <select
                  aria-label="Node type filter"
                  value={nodeType}
                  onChange={(e) => setNodeType(e.target.value)}
                >
                  <option value="">All nodes</option>
                  {[
                    "Component",
                    "File",
                    "Class",
                    "Interface",
                    "Function",
                    "Method",
                    "Endpoint",
                    "DatabaseEntity",
                    "ExternalPackage",
                  ].map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
                <select
                  aria-label="Relationship filter"
                  value={relationship}
                  onChange={(e) => setRelationship(e.target.value)}
                >
                  <option value="">All edges</option>
                  {[
                    "CALLS",
                    "IMPORTS",
                    "DEFINES",
                    "EXTENDS",
                    "IMPLEMENTS",
                    "HANDLES",
                    "DEPENDS_ON",
                    "READS_FROM",
                    "WRITES_TO",
                    "USES_PACKAGE",
                    "REFERENCES",
                  ].map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
                <select
                  aria-label="Graph layout"
                  value={layout}
                  onChange={(e) => setLayout(e.target.value)}
                >
                  <option value="cose">Force layout</option>
                  <option value="dagre">Hierarchy</option>
                  <option value="circle">Circle</option>
                  <option value="grid">Grid</option>
                </select>
              </div>
              {pathStart && (
                <div className="path-banner">
                  <GitBranch size={14} />
                  Path start: {pathStart.name}. Select a target, then Find
                  connection.
                  <button
                    className="icon-button"
                    onClick={() => setPathStart(null)}
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
              {pathNotice && <div className="path-banner">{pathNotice}</div>}
              <Graph
                data={filteredGraph}
                onSelect={(n) => void selectNode(n)}
                selected={selected?.id}
                highlights={highlights}
                layout={layout}
              />
              <div className="graph-status">
                <span>
                  {filteredGraph.nodes.length} nodes ·{" "}
                  {filteredGraph.edges.length} edges{" "}
                  {graph.truncated
                    ? "· Limited view, use search to explore more"
                    : ""}
                </span>
                <span>
                  {working ? (
                    <>
                      <LoaderCircle className="spin" size={12} />
                      {working}
                    </>
                  ) : (
                    <>
                      <ShieldCheck size={12} />
                      Static analysis evidence
                    </>
                  )}
                </span>
              </div>
            </>
          ) : (
            overview && (
              <div className="overview-panel">
                <div className="eyebrow">REPOSITORY INTELLIGENCE</div>
                <h2>The shape of your codebase</h2>
                <p className="muted">
                  Computed from the indexed source. Explore the architecture,
                  then follow the dependencies.
                </p>
                <div className="metric-grid">
                  {[
                    ["Source files", overview.files],
                    ["Lines of code", overview.lines],
                    ["Functions", overview.counts.Function || 0],
                    ["Classes", overview.counts.Class || 0],
                    ["Methods", overview.counts.Method || 0],
                    ["API endpoints", overview.counts.Endpoint || 0],
                    ["Graph nodes", overview.nodes],
                    ["Relationships", overview.relationships],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span>{label}</span>
                      <strong>{Number(value).toLocaleString()}</strong>
                    </div>
                  ))}
                </div>
                <button
                  className="button subtle"
                  onClick={() =>
                    void ask(
                      "Explain the architecture of this repository with evidence.",
                    )
                  }
                >
                  <Sparkles size={15} />
                  Explain this architecture
                </button>
                {overview.architecture && (
                  <div className="architecture-summary">
                    <h3>Architecture explanation</h3>
                    <p>{overview.architecture.answer}</p>
                    <div className="citations">
                      {overview.architecture.citations.map((c) => (
                        <button
                          key={c.symbol_id}
                          onClick={() => setCitation(c)}
                        >
                          <FileCode2 size={12} />
                          {c.file}:{c.start_line}
                        </button>
                      ))}
                    </div>
                    <span className="hint">
                      {overview.architecture.grounding === "static-evidence"
                        ? "Computed repository facts"
                        : "AI explanation with source evidence"}
                    </span>
                  </div>
                )}
                <h3>Most connected components</h3>
                <div className="hub-list">
                  {overview.hubs.map((h) => (
                    <button
                      key={h.node.id}
                      onClick={() => void selectNode(h.node)}
                    >
                      <span>
                        <strong>{h.node.name}</strong>
                        <small>{h.node.file_path}</small>
                      </span>
                      <div className="hub-bar">
                        <i
                          style={{
                            width:
                              (h.degree / (overview.hubs[0]?.degree || 1)) *
                                100 +
                              "%",
                          }}
                        />
                      </div>
                      <b>{h.degree}</b>
                    </button>
                  ))}
                </div>
                <h3>Architecture insights</h3>
                {overview.cycles.map((cycle, index) => (
                  <button
                    className="insight"
                    key={index}
                    onClick={() =>
                      void showEvidence({
                        symbols: cycle,
                        paths: [cycle],
                      } as Answer).catch(fail)
                    }
                  >
                    <AlertTriangle size={18} />
                    <span>
                      <strong>Circular dependency detected</strong>
                      <small>
                        {cycle.length - 1} components · Click to visualize the
                        cycle
                      </small>
                    </span>
                    <ArrowUpRight size={16} />
                  </button>
                ))}
                <div className="insight">
                  <Target size={18} />
                  <span>
                    <strong>
                      {overview.potentially_unused.length} potentially unused
                      symbols
                    </strong>
                    <small>
                      No incoming static references. Dynamic invocation may
                      still use them.
                    </small>
                  </span>
                </div>
                <div className="insight">
                  <GitBranch size={18} />
                  <span>
                    <strong>
                      {overview.unresolved_relationships} unresolved
                      relationships
                    </strong>
                    <small>
                      Excluded from dependency paths and impact calculations.
                    </small>
                  </span>
                </div>
                {overview.warnings?.map((w) => (
                  <p className="warning hint" key={w}>
                    {w}
                  </p>
                ))}
              </div>
            )
          )}
        </section>
        <aside className="right-panel">
          <div className="right-tabs">
            <button
              className={right === "assistant" ? "active" : ""}
              onClick={() => setRight("assistant")}
            >
              <Sparkles size={14} />
              Assistant
            </button>
            <button
              className={right === "inspect" ? "active" : ""}
              onClick={() => setRight("inspect")}
            >
              <Code2 size={14} />
              Inspector
            </button>
            {impact && (
              <button
                className={right === "impact" ? "active" : ""}
                onClick={() => setRight("impact")}
              >
                <Activity size={14} />
              </button>
            )}
            <button
              className="icon-button"
              title="Hide assistant"
              onClick={() => setRightOpen(false)}
            >
              <PanelRightClose size={14} />
            </button>
          </div>
          {right === "assistant" ? (
            <>
              <div className="chat-messages">
                {messages.length === 0 ? (
                  <div className="chat-welcome">
                    <div className="assistant-symbol">
                      <Sparkles size={25} />
                    </div>
                    <div className="eyebrow">YOUR CODE, CONNECTED</div>
                    <h2>Ask your codebase.</h2>
                    <p>
                      Explore how things work, find dependencies, or understand
                      what a change might affect.
                    </p>
                    <div className="suggestions">
                      {[
                        "Where is authentication handled?",
                        "Trace POST /checkout to the database.",
                        "What breaks if PaymentService changes?",
                        "How is this repository structured?",
                      ].map((q) => (
                        <button key={q} onClick={() => void ask(q)}>
                          {q}
                          <ArrowUpRight size={14} />
                        </button>
                      ))}
                    </div>
                    <div className="evidence-note">
                      <ShieldCheck size={16} />
                      <span>
                        Answers use retrieved code and graph evidence, with
                        clickable source citations.
                      </span>
                    </div>
                  </div>
                ) : (
                  messages.map((m, index) => (
                    <div key={index} className={"chat-message " + m.role}>
                      <div className="message-label">
                        {m.role === "assistant" ? (
                          <>
                            <Sparkles size={13} />
                            REPOGRAPH
                          </>
                        ) : (
                          "YOU"
                        )}
                        {m.result && (
                          <span>
                            {m.result.grounding === "static-evidence"
                              ? "Static evidence"
                              : `${Math.round(m.result.confidence * 100)}% confidence`}
                          </span>
                        )}
                      </div>
                      <div className="message-content">{m.content}</div>
                      {m.result && (
                        <>
                          <div className="citations">
                            {m.result.citations.map((c, index) => (
                              <button
                                key={c.symbol_id + index}
                                onClick={() => setCitation(c)}
                                title={`${c.file}:${c.start_line}–${c.end_line}`}
                              >
                                <FileCode2 size={12} />
                                {c.file.split("/").pop()}
                                <span>
                                  L{c.start_line}–{c.end_line}
                                </span>
                              </button>
                            ))}
                          </div>
                          {m.result.symbols.length > 0 && (
                            <button
                              className="evidence-button"
                              onClick={() =>
                                void showEvidence(m.result!).catch(fail)
                              }
                            >
                              <Network size={13} />
                              Highlight evidence
                              <ArrowUpRight size={13} />
                            </button>
                          )}
                          {m.result.warning && (
                            <details className="response-detail">
                              <summary>Provider status</summary>
                              <p>{m.result.warning}</p>
                            </details>
                          )}
                          <details className="response-detail">
                            <summary>
                              {m.result.tool_calls.length} evidence tools used
                            </summary>
                            {m.result.tool_calls.map((t, i) => (
                              <p key={i}>{t.name.replaceAll("_", " ")}</p>
                            ))}
                          </details>
                        </>
                      )}
                    </div>
                  ))
                )}
                {asking && (
                  <div className="thinking">
                    <LoaderCircle className="spin" size={15} />
                    Retrieving evidence and reasoning…
                  </div>
                )}
              </div>
              <form
                className="chat-compose"
                onSubmit={(e) => {
                  e.preventDefault();
                  void ask();
                }}
              >
                {selected && (
                  <div className="chat-context">
                    <Code2 size={12} />
                    {selected.name}
                    <button
                      title="Clear selected context"
                      type="button"
                      onClick={() => setSelected(null)}
                    >
                      <X size={12} />
                    </button>
                  </div>
                )}
                <textarea
                  aria-label="Ask a question about this repository"
                  placeholder="Ask about this repository…"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void ask();
                    }
                  }}
                  rows={3}
                />
                <div>
                  <span>↵ Send · ⇧ ↵ New line</span>
                  <button
                    className="send-button"
                    aria-label="Send question"
                    disabled={asking || !question.trim()}
                  >
                    <Send size={15} />
                  </button>
                </div>
              </form>
            </>
          ) : right === "inspect" ? (
            selected ? (
              <div className="inspector">
                <div className="node-type">
                  {selected.type}
                  <span>{selected.language}</span>
                </div>
                <h2>{selected.name}</h2>
                <button
                  className="source-location"
                  onClick={() => openSource(selected)}
                >
                  <FileCode2 size={14} />
                  {selected.file_path}
                  <ArrowUpRight size={13} />
                </button>
                <p className="hint">
                  Lines {selected.start_line}–{selected.end_line}
                </p>
                {selected.signature && (
                  <pre className="signature">{selected.signature}</pre>
                )}
                {selected.docstring && (
                  <p className="docstring">{selected.docstring}</p>
                )}
                <button
                  className="button primary full"
                  disabled={!!working}
                  onClick={() => void analyzeImpact()}
                >
                  <Activity size={16} />
                  Analyze Impact
                  <ArrowRight size={15} />
                </button>
                <div className="inspector-actions">
                  <button
                    onClick={() =>
                      void ask(`Explain ${selected.name} and its dependencies.`)
                    }
                  >
                    <MessageSquare size={15} />
                    Ask about this
                  </button>
                  <button onClick={() => openSource(selected)}>
                    <BookOpen size={15} />
                    Open source
                  </button>
                  <button onClick={() => void expand("in", "CALLS")}>
                    <ArrowDownLeft size={15} />
                    Show callers
                  </button>
                  <button onClick={() => void expand("out", "CALLS")}>
                    <ArrowUpRight size={15} />
                    Show callees
                  </button>
                </div>
                <div className="inspector-section">
                  <div className="section-label">EXPLORE NEIGHBORHOOD</div>
                  <div className="inline-controls">
                    <select
                      aria-label="Neighborhood depth"
                      value={depth}
                      onChange={(e) => setDepth(Number(e.target.value))}
                    >
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={n}>
                          {n} hop{n > 1 ? "s" : ""}
                        </option>
                      ))}
                    </select>
                    <button
                      className="button subtle small"
                      onClick={() => void expand()}
                    >
                      Expand <Expand size={13} />
                    </button>
                    <button
                      className="button subtle small"
                      onClick={() => {
                        setGraph({ nodes: [selected], edges: [] });
                        setHighlights([]);
                      }}
                    >
                      Collapse
                    </button>
                  </div>
                  <div className="inspector-actions">
                    <button onClick={() => setPathStart(selected)}>
                      <Target size={15} />
                      Set path start
                    </button>
                    <button onClick={() => void trace()}>
                      <GitBranch size={15} />
                      {pathStart ? "Find connection" : "Trace downstream"}
                    </button>
                  </div>
                </div>
                <div className="inspector-section">
                  <div className="section-label">RELATIONSHIPS</div>
                  {(["incoming", "outgoing"] as const).map((direction) => (
                    <details key={direction} open>
                      <summary>
                        {direction === "incoming" ? "Incoming" : "Outgoing"}{" "}
                        <span>{edges[direction].length}</span>
                      </summary>
                      {edges[direction].map((e) => (
                        <button
                          className="relationship-row"
                          key={e.id}
                          onClick={() => {
                            const target =
                              direction === "incoming" ? e.source : e.target;
                            void api<{ node: Node }>(
                              base + "/symbols/" + target,
                            )
                              .then((r) => selectNode(r.node))
                              .catch(fail);
                          }}
                        >
                          <span>{e.type.replaceAll("_", " ")}</span>
                          <small>
                            {e.source_file?.split("/").pop()}:{e.source_line} ·{" "}
                            {e.resolution}
                          </small>
                        </button>
                      ))}
                    </details>
                  ))}
                </div>
              </div>
            ) : (
              <div className="empty">
                <Target size={30} />
                <h3>Select a node</h3>
                <p>Inspect its source, callers, and dependencies.</p>
              </div>
            )
          ) : (
            impact && (
              <div className="impact-panel">
                <div className="eyebrow">CHANGE IMPACT</div>
                <h2>Know the blast radius.</h2>
                <div className={"risk-score " + impact.risk.toLowerCase()}>
                  <strong>
                    {impact.score}
                    <small>/ 100</small>
                  </strong>
                  <span>{impact.risk} RISK</span>
                </div>
                <p className="muted">Computed from static dependencies.</p>
                <div className="impact-stats">
                  {[
                    ["Dependents", impact.blast_radius],
                    ["Files", impact.affected_files.length],
                    ["API routes", impact.affected_endpoints.length],
                    ["Max depth", impact.dependency_depth],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <strong>{value}</strong>
                      <span>{label}</span>
                    </div>
                  ))}
                </div>
                <h3>What contributes to this score</h3>
                {Object.entries(impact.features).map(([key, value]) => (
                  <div className="score-feature" key={key}>
                    <span>{key.replaceAll("_", " ")}</span>
                    <b>+{value}</b>
                  </div>
                ))}
                <h3>Affected files</h3>
                {impact.affected_files.map((file) => (
                  <button
                    key={file}
                    className="affected-file"
                    onClick={() =>
                      setCitation({
                        symbol_id: "",
                        file,
                        start_line: 1,
                        end_line: 1,
                      })
                    }
                  >
                    <FileCode2 size={13} />
                    {file}
                    <ArrowUpRight size={12} />
                  </button>
                ))}
                <h3>Important paths</h3>
                {impact.paths.slice(0, 4).map((path, index) => (
                  <button
                    className="impact-path"
                    key={index}
                    onClick={() => setHighlights(path)}
                  >
                    {path
                      .map(
                        (n) =>
                          impact.graph.nodes.find((x) => x.id === n)?.name ||
                          "…",
                      )
                      .join(" → ")}
                  </button>
                ))}
                <button
                  className="button subtle full"
                  onClick={() =>
                    void ask("What could break if I change this symbol?")
                  }
                >
                  <Sparkles size={15} />
                  Explain this impact
                </button>
                <p className="hint">{impact.caveat}</p>
              </div>
            )
          )}
        </aside>
      </div>
      {citation && (
        <SourceViewer
          repository={id}
          citation={citation}
          onClose={() => setCitation(null)}
        />
      )}
    </div>
  );
}
function PlusIcon() {
  return (
    <span aria-hidden="true" style={{ fontSize: 18, lineHeight: 1 }}>
      +
    </span>
  );
}
