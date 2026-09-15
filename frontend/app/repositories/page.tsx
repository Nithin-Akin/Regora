"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Plus,
  FolderGit2,
  ArrowUpRight,
  Trash2,
  LoaderCircle,
} from "lucide-react";
import Brand from "@/components/Brand";
import { api } from "@/lib/api";
import type { Repository } from "@/lib/types";
export default function Repositories() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
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
  return (
    <>
      <header className="topbar">
        <Brand />
        <Link className="button primary" href="/">
          <Plus size={16} />
          Add repository
        </Link>
      </header>
      <main className="history">
        <div className="eyebrow">YOUR WORKSPACE</div>
        <h1>Repositories</h1>
        <p className="muted">
          Pick up where you left off. Every graph starts with your source.
        </p>
        {error && <div className="error">{error}</div>}
        {busy ? (
          <div className="empty">
            <LoaderCircle className="spin" />
            Loading repositories…
          </div>
        ) : repos.length === 0 ? (
          <div className="empty">
            <FolderGit2 size={40} />
            <h2>No repositories yet</h2>
            <p>Import a repository or explore the included demo.</p>
            <Link href="/" className="button primary">
              Analyze a repository <ArrowUpRight size={16} />
            </Link>
          </div>
        ) : (
          <div className="repo-list">
            {repos.map((r) => (
              <article key={r.id}>
                <Link href={"/repository/" + r.id}>
                  <div className="icon-well">
                    <FolderGit2 size={24} />
                  </div>
                  <div>
                    <h2>{r.name}</h2>
                    <p>
                      {new Date(r.created_at).toLocaleDateString()} ·{" "}
                      {r.message}
                    </p>
                  </div>
                  <span className={"status " + r.status.toLowerCase()}>
                    {r.status}
                  </span>
                  <ArrowUpRight size={18} />
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
          </div>
        )}
      </main>
    </>
  );
}
