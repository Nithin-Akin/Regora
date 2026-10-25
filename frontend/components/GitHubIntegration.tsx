"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  ExternalLink,
  GitPullRequest,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Webhook,
} from "lucide-react";
import { api } from "@/lib/api";
import type { GitHubIntegration as Integration, GuardianRun } from "@/lib/types";

function runTime(run: GuardianRun) {
  const value = run.completed_at || run.failed_at || run.started_at || run.created_at;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

export default function GitHubIntegration({ base }: { base: string }) {
  const [integration, setIntegration] = useState<Integration | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      setIntegration(await api<Integration>(base + "/github-integration"));
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

  const active = useMemo(
    () => integration?.runs.some((run) => ["QUEUED", "RUNNING"].includes(run.status)),
    [integration],
  );

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => void load(true), 4000);
    return () => window.clearInterval(timer);
  }, [active, load]);

  async function retry(run: GuardianRun) {
    setRetrying(run.id);
    setNotice("");
    try {
      const result = await api<{ status: string }>(
        `${base}/github-integration/runs/${encodeURIComponent(run.id)}/retry`,
        { method: "POST" },
      );
      setNotice(result.status === "duplicate" ? "Retry is already queued" : "Review retry queued");
      await load(true);
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setRetrying("");
    }
  }

  async function copyWebhookPath() {
    const path = integration?.webhook_path;
    if (!path) return;
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${path}`);
      setNotice("Webhook URL copied");
    } catch {
      setNotice("Could not copy the webhook URL");
    }
  }

  if (loading) {
    return <div className="empty"><LoaderCircle className="spin" />Loading GitHub integration…</div>;
  }
  if (!integration) {
    return <div className="empty"><AlertTriangle /><h3>Integration unavailable</h3><p>{error}</p></div>;
  }

  const checks = [
    ["Authentication", integration.authentication !== "MISSING", integration.authentication.replaceAll("_", " ")],
    ["Signed webhooks", integration.webhook_configured, integration.webhook_configured ? "Configured" : "Missing secret"],
    ["Repository binding", integration.repository.bound, integration.repository.bound ? `Installation ${integration.repository.installation_id}` : "Waiting for installation"],
  ] as const;

  return (
    <div className="integration-panel">
      <div className="integration-heading">
        <div>
          <div className="eyebrow">GITHUB INTEGRATION</div>
          <h2>PR Guardian operations</h2>
          <p className="muted">Monitor the connection, inspect every automatic review, and retry failures.</p>
        </div>
        <button className="button subtle small" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <section className={`integration-status ${integration.status.toLowerCase()}`}>
        <span className="integration-status-icon">
          {integration.status === "READY" ? <ShieldCheck /> : <AlertTriangle />}
        </span>
        <div>
          <span>{integration.status === "READY" ? "CONNECTED" : "SETUP REQUIRED"}</span>
          <strong>{integration.status === "READY" ? "Automatic pull request reviews are ready." : "Finish the steps below to activate PR Guardian."}</strong>
        </div>
      </section>

      <div className="integration-checks">
        {checks.map(([label, passed, detail]) => (
          <div key={label} className={passed ? "passed" : "missing"}>
            <span>{passed ? <Check size={15} /> : <AlertTriangle size={15} />}{label}</span>
            <strong>{detail}</strong>
          </div>
        ))}
      </div>

      <section className="webhook-card">
        <span><Webhook size={16} /> Webhook endpoint</span>
        <code>{integration.webhook_path}</code>
        <button className="icon-button" title="Copy complete webhook URL" onClick={() => void copyWebhookPath()}>
          <Copy size={14} />
        </button>
      </section>

      {integration.setup_steps.length > 0 && (
        <section className="setup-steps">
          <h3>Next setup steps</h3>
          <ol>{integration.setup_steps.map((step) => <li key={step}>{step}</li>)}</ol>
          <a href="https://github.com/Nithin-Akin/Regora/blob/main/docs/GITHUB_PR_GUARDIAN.md" target="_blank" rel="noreferrer">
            Open setup guide <ExternalLink size={13} />
          </a>
        </section>
      )}

      <div className="run-history-heading">
        <div><h3>Review history</h3><span>{integration.runs.length} recent runs</span></div>
        {(notice || error) && <span className={error ? "danger" : "success"}>{error || notice}</span>}
      </div>
      <div className="guardian-runs">
        {integration.runs.length === 0 ? (
          <div className="integration-empty"><ShieldCheck size={24} /><strong>No reviews yet</strong><span>Open or update a pull request after connecting the GitHub App.</span></div>
        ) : integration.runs.map((run) => (
          <article className="guardian-run" key={run.id}>
            <span className={`run-state ${run.status.toLowerCase()}`}>
              {["QUEUED", "RUNNING"].includes(run.status) && <LoaderCircle className="spin" size={13} />}
              {run.status === "COMPLETE" && <Check size={13} />}
              {run.status === "ERROR" && <AlertTriangle size={13} />}
              {run.status}
            </span>
            <div className="run-main">
              <a href={run.pr_url} target="_blank" rel="noreferrer">
                <GitPullRequest size={15} /> PR #{run.pull_request || "?"}
                <ExternalLink size={12} />
              </a>
              <span>{run.command || "review"} · {run.head_sha?.slice(0, 8) || "unknown commit"}</span>
              {run.error && <small>{run.error}</small>}
            </div>
            <div className="run-actions">
              <time>{runTime(run)}</time>
              {run.comment_url && <a href={run.comment_url} target="_blank" rel="noreferrer">Open review <ExternalLink size={12} /></a>}
              {run.status === "ERROR" && (
                <button className="button subtle small" disabled={!!retrying} onClick={() => void retry(run)}>
                  {retrying === run.id ? <LoaderCircle className="spin" size={13} /> : <RefreshCw size={13} />}
                  Retry
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
