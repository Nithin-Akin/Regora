"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Database,
  FileCode2,
  GitCompareArrows,
  History,
  LoaderCircle,
  Network,
  RefreshCw,
  Route,
} from "lucide-react";
import { api } from "@/lib/api";
import type { GitHubIntegration, GraphDiff, GraphVersion, VersionHistory } from "@/lib/types";

const ACTIVE_SYNC = new Set(["QUEUED", "CLONING", "SCANNING", "PARSING", "BUILDING_GRAPH", "EMBEDDING", "ANALYZING"]);

function shortSha(sha: string) {
  return sha ? sha.slice(0, 8) : "unknown";
}

function versionLabel(version: GraphVersion) {
  const date = new Date(version.created_at);
  const timestamp = Number.isNaN(date.valueOf()) ? version.created_at : date.toLocaleString();
  return `${shortSha(version.commit_sha)} · ${timestamp}${version.current ? " · current" : ""}`;
}

export default function VersionChanges({ base }: { base: string }) {
  const [integration, setIntegration] = useState<GitHubIntegration | null>(null);
  const [history, setHistory] = useState<VersionHistory | null>(null);
  const [baseSha, setBaseSha] = useState("");
  const [headSha, setHeadSha] = useState("");
  const [diff, setDiff] = useState<GraphDiff | null>(null);
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const [nextIntegration, nextHistory] = await Promise.all([
        api<GitHubIntegration>(base + "/github-integration"),
        api<VersionHistory>(base + "/versions"),
      ]);
      setIntegration(nextIntegration);
      setHistory(nextHistory);
      setBaseSha((current) =>
        nextHistory.versions.some((version) => version.commit_sha === current)
          ? current
          : nextHistory.versions[1]?.commit_sha || "",
      );
      setHeadSha((current) =>
        nextHistory.versions.some((version) => version.commit_sha === current)
          ? current
          : nextHistory.versions[0]?.commit_sha || "",
      );
      setError("");
    } catch (value) {
      setError((value as Error).message);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [base]);

  useEffect(() => {
    void load();
  }, [load]);

  const syncActive = useMemo(
    () => ACTIVE_SYNC.has(integration?.sync.status || ""),
    [integration?.sync.status],
  );

  useEffect(() => {
    if (!syncActive) return;
    const timer = window.setInterval(() => void load(true), 3000);
    return () => window.clearInterval(timer);
  }, [load, syncActive]);

  const compare = useCallback(async () => {
    if (!baseSha || !headSha || baseSha === headSha) {
      setDiff(null);
      return;
    }
    setComparing(true);
    try {
      setDiff(await api<GraphDiff>(`${base}/versions/compare?base_sha=${baseSha}&head_sha=${headSha}`));
      setError("");
    } catch (value) {
      setError((value as Error).message);
      setDiff(null);
    } finally {
      setComparing(false);
    }
  }, [base, baseSha, headSha]);

  useEffect(() => {
    void compare();
  }, [compare]);

  if (loading) {
    return <div className="empty"><LoaderCircle className="spin" />Loading repository history…</div>;
  }

  const versions = history?.versions || [];
  const sync = integration?.sync;
  const syncState = sync?.status || "NOT_SYNCED";
  const syncHealthy = syncState === "CURRENT";

  return (
    <div className="changes-panel">
      <div className="changes-heading">
        <div>
          <div className="eyebrow">LIVE REPOSITORY INTELLIGENCE</div>
          <h2>See what changed between commits</h2>
          <p className="muted">Compare retained code graphs using static evidence from each indexed version.</p>
        </div>
        <button className="button subtle small" onClick={() => void load()}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <section className={`sync-card ${syncState.toLowerCase()}`}>
        <span className="sync-icon">
          {syncActive ? <LoaderCircle className="spin" /> : syncHealthy ? <CheckCircle2 /> : <History />}
        </span>
        <div>
          <span>{syncState.replaceAll("_", " ")}</span>
          <strong>{sync?.message || (syncHealthy ? "The indexed graph matches GitHub." : "Waiting for a default branch push.")}</strong>
          {sync?.error && <small>{sync.error}</small>}
        </div>
        <div className="sync-commits">
          <span>Indexed <code>{shortSha(sync?.indexed_sha || "")}</code></span>
          <ArrowRight size={13} />
          <span>GitHub <code>{shortSha(sync?.latest_github_sha || "")}</code></span>
        </div>
      </section>

      {error && <div className="changes-error"><AlertTriangle size={15} />{error}</div>}

      {versions.length < 2 ? (
        <section className="changes-empty">
          <GitCompareArrows size={30} />
          <h3>Two indexed commits are required</h3>
          <p>Reindex this GitHub repository or push to its default branch. Regora will retain each successful graph version here.</p>
          <span>{versions.length} of 2 versions available</span>
        </section>
      ) : (
        <>
          <section className="version-picker">
            <label>
              <span>BASE VERSION</span>
              <select value={baseSha} onChange={(event) => setBaseSha(event.target.value)}>
                {versions.map((version) => <option key={version.id} value={version.commit_sha}>{versionLabel(version)}</option>)}
              </select>
            </label>
            <ArrowRight size={18} />
            <label>
              <span>HEAD VERSION</span>
              <select value={headSha} onChange={(event) => setHeadSha(event.target.value)}>
                {versions.map((version) => <option key={version.id} value={version.commit_sha}>{versionLabel(version)}</option>)}
              </select>
            </label>
          </section>

          {baseSha === headSha ? (
            <div className="changes-empty compact"><History size={24} /><p>Choose two different commits.</p></div>
          ) : comparing ? (
            <div className="changes-empty compact"><LoaderCircle className="spin" /><p>Comparing code graphs…</p></div>
          ) : diff ? (
            <>
              <section className={`diff-risk ${diff.risk.level.toLowerCase()}`}>
                <div><span>{diff.risk.score}</span><small>/ 100</small></div>
                <div><strong>{diff.risk.level} CHANGE RISK</strong><small>Computed from structural graph changes</small></div>
              </section>

              <div className="diff-metrics">
                <div><strong>+{diff.summary.symbols.added}</strong><span>Symbols added</span></div>
                <div><strong>−{diff.summary.symbols.removed}</strong><span>Symbols removed</span></div>
                <div><strong>{diff.summary.symbols.modified}</strong><span>Symbols modified</span></div>
                <div><strong>{diff.summary.relationships.added + diff.summary.relationships.removed + diff.summary.relationships.modified}</strong><span>Relationship changes</span></div>
              </div>

              <div className="affected-metrics">
                <span><FileCode2 size={15} /><b>{diff.summary.affected_files}</b> files</span>
                <span><Network size={15} /><b>{diff.summary.affected_modules}</b> modules</span>
                <span><Route size={15} /><b>{diff.summary.affected_endpoints}</b> endpoints</span>
                <span><Database size={15} /><b>{diff.summary.affected_database_entities}</b> database entities</span>
              </div>

              <section className="diff-evidence">
                <div className="diff-section-heading"><h3>Changed symbols</h3><span>{diff.symbols.length} evidence items</span></div>
                {diff.symbols.length === 0 ? <p className="muted">No symbol changes.</p> : (
                  <div className="diff-list">
                    {diff.symbols.map((item) => (
                      <article key={`${item.change}-${item.id}`}>
                        <span className={`change-badge ${item.change}`}>{item.change}</span>
                        <div><strong>{item.qualified_name || item.name}</strong><small>{item.file_path || item.type}{item.start_line ? `:${item.start_line}` : ""}</small></div>
                        {item.changed_fields?.length ? <code>{item.changed_fields.join(", ")}</code> : null}
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="diff-evidence">
                <div className="diff-section-heading"><h3>Relationship changes</h3><span>{diff.relationships.length} evidence items</span></div>
                {diff.relationships.length === 0 ? <p className="muted">No relationship changes.</p> : (
                  <div className="diff-list">
                    {diff.relationships.map((item) => (
                      <article key={`${item.change}-${item.id}`}>
                        <span className={`change-badge ${item.change}`}>{item.change}</span>
                        <div><strong>{item.source_name} <ArrowRight size={12} /> {item.target_name}</strong><small>{item.type} · {item.source_file || "structural evidence"}{item.source_line ? `:${item.source_line}` : ""}</small></div>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <p className="changes-limit"><AlertTriangle size={13} />{diff.limitations}{diff.truncated ? " Evidence is truncated to the first 200 items per category." : ""}</p>
            </>
          ) : null}
        </>
      )}
    </div>
  );
}
