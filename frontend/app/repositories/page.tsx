"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Plus,
  FolderGit2,
  ArrowUpRight,
  Trash2,
  LoaderCircle,
  Search,
  CheckCircle2,
  Activity,
  AlertTriangle,
  Clock3,
} from "lucide-react";
import Brand from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import AccountMenu from "@/components/AccountMenu";
import { api } from "@/lib/api";
import type { Repository } from "@/lib/types";
export default function Repositories() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    api<Repository[]>("/repositories")
      .then(setRepos)
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  }, []);
  async function remove(r: Repository) {
    if (!confirm(`Delete ${r.name} and its indexed graph?`)) return;
    try {
      await api("/repositories/" + r.id, { method: "DELETE" });
      setRepos(repos.filter((x) => x.id !== r.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const ready = repos.filter((repo) => repo.status === "READY").length;
  const failed = repos.filter((repo) => repo.status === "FAILED").length;
  const active = repos.length - ready - failed;
  const filtered = repos.filter((repo) =>
    repo.name.toLowerCase().includes(query.trim().toLowerCase()),
  );
  return (
    <>
      <header className="topbar">
        <Brand />
        <div className="topbar-actions">
          <ThemeToggle />
          <AccountMenu />
          <Link className="button primary" href="/">
            <Plus size={16} />
            Add repository
          </Link>
        </div>
      </header>
      <main className="history repo-dashboard">
        <div className="dashboard-heading">
          <div>
            <div className="eyebrow">YOUR WORKSPACE</div>
            <h1>Repositories</h1>
            <p className="muted">
              Continue exploring an indexed codebase or start a new analysis.
            </p>
          </div>
          {!busy && repos.length > 0 && (
            <div className="dashboard-stats" aria-label="Repository summary">
              <div>
                <CheckCircle2 size={17} />
                <strong>{ready}</strong>
                <span>Ready</span>
              </div>
              <div>
                <Activity size={17} />
                <strong>{active}</strong>
                <span>Processing</span>
              </div>
              <div>
                <AlertTriangle size={17} />
                <strong>{failed}</strong>
                <span>Needs attention</span>
              </div>
            </div>
          )}
        </div>
        {error && <div className="error">{error}</div>}
        {busy ? (
          <div className="empty">
            <LoaderCircle className="spin" />
            Loading repositories…
          </div>
        ) : repos.length === 0 ? (
          <div className="empty dashboard-empty">
            <div className="icon-well">
              <FolderGit2 size={25} />
            </div>
            <h2>No repositories yet</h2>
            <p>Import from GitHub, upload a ZIP, or explore the included demo.</p>
            <Link href="/" className="button primary">
              Analyze a repository <ArrowUpRight size={16} />
            </Link>
          </div>
        ) : (
          <>
            <div className="dashboard-toolbar">
              <Search size={16} />
              <input
                aria-label="Search repositories"
                placeholder="Search repositories…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <span>{filtered.length} repositories</span>
            </div>
            <div className="repo-list">
            {filtered.map((r) => (
              <article key={r.id}>
                <Link href={"/repository/" + r.id}>
                  <div className="repo-card-heading">
                    <div className="icon-well">
                      <FolderGit2 size={21} />
                    </div>
                    <span className={"status " + r.status.toLowerCase()}>
                      {r.status}
                    </span>
                  </div>
                  <h2>{r.name}</h2>
                  <p>{r.message}</p>
                  {r.status !== "READY" && r.status !== "FAILED" && (
                    <div className="repo-progress" aria-label={`${r.progress}% indexed`}>
                      <i style={{ width: `${r.progress}%` }} />
                    </div>
                  )}
                  <div className="repo-card-footer">
                    <span>
                      <Clock3 size={13} />
                      {new Date(r.created_at).toLocaleDateString()}
                    </span>
                    <strong>
                      Open workspace <ArrowUpRight size={14} />
                    </strong>
                  </div>
                </Link>
                <button
                  className="icon-button danger"
                  title="Delete repository"
                  onClick={() => void remove(r)}
                >
                  <Trash2 size={16} />
                </button>
              </article>
            ))}
            {filtered.length === 0 && (
              <div className="empty dashboard-search-empty">
                <Search size={25} />
                <h2>No matching repositories</h2>
                <p>Try a different repository name.</p>
              </div>
            )}
            </div>
          </>
        )}
      </main>
    </>
  );
}
