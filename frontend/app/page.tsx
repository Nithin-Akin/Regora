"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight,
  Upload,
  GitBranch,
  FolderGit2,
  ShieldCheck,
  ScanLine,
  Workflow,
  LoaderCircle,
  Terminal,
  FileArchive,
} from "lucide-react";
import Brand from "@/components/Brand";
import { api, uploadRepository } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"github" | "zip">("github");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  async function analyze(demo = false) {
    setBusy(true);
    setError("");
    try {
      let result: { id: string };
      if (demo) result = await api("/repositories/demo", { method: "POST" });
      else if (mode === "zip") {
        if (!file) throw new Error("Choose a repository ZIP first.");
        result = await uploadRepository(file, setProgress);
      } else
        result = await api("/repositories/github", {
          method: "POST",
          body: JSON.stringify({ url }),
        });
      router.push("/repository/" + result.id);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <div className="landing">
      <header className="topbar">
        <Brand />
        <nav>
          <Link href="/repositories">
            <FolderGit2 size={16} />
            Your repositories
          </Link>
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            API docs <ArrowRight size={14} />
          </a>
        </nav>
      </header>
      <main className="landing-main">
        <div className="intro">
          <div className="eyebrow">
            <span className="tiny-line" />
            CODE INTELLIGENCE, WITH EVIDENCE
          </div>
          <h1>
            Understand unfamiliar
            <br />
            codebases <em>visually.</em>
          </h1>
          <p className="intro-copy">
            Understand a codebase before you break it.
          </p>
          <p className="muted explanation">
            RepoGraph maps your code into an intelligent dependency graph and
            lets you ask questions about architecture, dependencies and change
            impact.
          </p>
        </div>
        <section className="ingest-card">
          <div className="card-heading">
            <div className="icon-well">
              <FolderGit2 size={23} />
            </div>
            <div>
              <h2>Start with a repository</h2>
              <p>Bring your code. We’ll connect the dots.</p>
            </div>
          </div>
          <div className="segmented" role="tablist" aria-label="Import method">
            <button
              role="tab"
              aria-selected={mode === "github"}
              className={mode === "github" ? "active" : ""}
              onClick={() => setMode("github")}
            >
              <GitBranch size={16} />
              GitHub URL
            </button>
            <button
              role="tab"
              aria-selected={mode === "zip"}
              className={mode === "zip" ? "active" : ""}
              onClick={() => setMode("zip")}
            >
              <Upload size={16} />
              Upload ZIP
            </button>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void analyze();
            }}
          >
            {mode === "github" ? (
              <div className="form-field">
                <label htmlFor="repo-url">Public repository URL</label>
                <div className="input-icon">
                  <GitBranch size={17} />
                  <input
                    id="repo-url"
                    placeholder="https://github.com/owner/repository"
                    type="url"
                    required
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    disabled={busy}
                  />
                </div>
                <p className="hint">
                  Python, JavaScript, and TypeScript supported.
                </p>
              </div>
            ) : (
              <label
                className={"dropzone " + (drag ? "dragging" : "")}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDrag(true);
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDrag(false);
                  setFile(e.dataTransfer.files[0] || null);
                }}
              >
                <FileArchive size={30} />
                <strong>
                  {file ? file.name : "Drop your repository here"}
                </strong>
                <span>
                  {file
                    ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
                    : "or click to choose a ZIP · up to 50 MB"}
                </span>
                <input
                  aria-label="Repository ZIP"
                  type="file"
                  accept=".zip"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  disabled={busy}
                />
              </label>
            )}
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            <button
              className="button primary full"
              disabled={busy}
              type="submit"
            >
              {busy ? (
                <>
                  <LoaderCircle className="spin" size={18} />
                  {progress > 0 && progress < 100
                    ? `Uploading ${progress}%`
                    : "Starting analysis…"}
                </>
              ) : (
                <>
                  Analyze Repository
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>
          <div className="secure-note">
            <ShieldCheck size={14} />
            Static analysis only. Your code is never executed.
          </div>
          <div className="demo-row">
            <div>
              <strong>Just exploring?</strong>
              <span>Try a commerce app with real dependencies.</span>
            </div>
            <button
              className="button subtle"
              disabled={busy}
              onClick={() => void analyze(true)}
            >
              Open demo <ArrowRight size={16} />
            </button>
          </div>
        </section>
        <div className="feature-strip">
          <div>
            <ScanLine size={21} />
            <strong>See the structure</strong>
            <span>Files, symbols, APIs, and their connections.</span>
          </div>
          <div>
            <Workflow size={21} />
            <strong>Trace the impact</strong>
            <span>Find what depends on the code you change.</span>
          </div>
          <div>
            <Terminal size={21} />
            <strong>Ask with confidence</strong>
            <span>Answers grounded in actual source evidence.</span>
          </div>
        </div>
      </main>
      <footer>
        <span>REPOGRAPH</span>
        <span>Code is the source of truth.</span>
        <span>Python / JavaScript / TypeScript</span>
      </footer>
    </div>
  );
}
