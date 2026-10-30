"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  FileCode2,
  GitBranch,
  ListChecks,
  LoaderCircle,
  Network,
  Sparkles,
  Target,
  Workflow,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Node, RefactoringPlan } from "@/lib/types";

export default function RefactoringPlanPanel({
  base,
  selected,
  onOpenSource,
  onShowEvidence,
}: {
  base: string;
  selected: Node | null;
  onOpenSource: (node: Node) => void;
  onShowEvidence: (plan: RefactoringPlan) => void;
}) {
  const [goal, setGoal] = useState("");
  const [plan, setPlan] = useState<RefactoringPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setGoal("");
    setPlan(null);
    setError("");
  }, [selected?.id]);

  const evidence = useMemo(
    () => new Map(plan?.citations.map((node) => [node.id, node]) || []),
    [plan],
  );
  const graphNodes = useMemo(
    () => new Map(plan?.graph.nodes.map((node) => [node.id, node]) || []),
    [plan],
  );

  async function generate(event: React.FormEvent) {
    event.preventDefault();
    if (!selected || goal.trim().length < 10) return;
    setLoading(true);
    setError("");
    try {
      const result = await api<RefactoringPlan>(base + "/refactoring-plan", {
        method: "POST",
        body: JSON.stringify({ symbol_id: selected.id, goal: goal.trim() }),
      });
      setPlan(result);
      onShowEvidence(result);
    } catch (value) {
      setError((value as Error).message);
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }

  if (!selected) {
    return (
      <div className="empty">
        <Target size={30} />
        <h3>Select a symbol</h3>
        <p>Choose a function, class, method, file, or endpoint to plan its change.</p>
      </div>
    );
  }

  return (
    <div className="refactor-panel">
      <div className="eyebrow">GROUNDED REFACTORING PLANNER</div>
      <h2>Plan the change before editing.</h2>
      <button className="refactor-target" onClick={() => onOpenSource(selected)}>
        <Target size={15} />
        <span><strong>{selected.name}</strong><small>{selected.file_path}:{selected.start_line}</small></span>
        <ArrowRight size={14} />
      </button>

      <form className="refactor-form" onSubmit={generate}>
        <label htmlFor="refactor-goal">What do you want to change?</label>
        <textarea
          id="refactor-goal"
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          placeholder={`Example: Extract ${selected.name} behind a stable interface without breaking existing callers.`}
          maxLength={2000}
          rows={5}
        />
        <div><span>{goal.length.toLocaleString()} / 2,000</span><span>Minimum 10 characters</span></div>
        <button className="button primary full" disabled={loading || goal.trim().length < 10}>
          {loading ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}
          {loading ? "Building grounded plan" : "Generate refactoring plan"}
        </button>
      </form>

      {error && <div className="refactor-error"><AlertTriangle size={15} />{error}</div>}

      {plan && (
        <>
          <section className={`refactor-risk ${plan.impact.risk.toLowerCase()}`}>
            <div><strong>{plan.impact.score}<small>/ 100</small></strong><span>{plan.impact.risk} RISK</span></div>
            <p>{plan.summary}</p>
            <span>{plan.grounding === "llm-with-evidence" ? `${Math.round(plan.confidence * 100)}% model confidence` : "Deterministic evidence plan"}</span>
          </section>

          <div className="refactor-stats">
            <div><strong>{plan.impact.blast_radius}</strong><span>Dependents</span></div>
            <div><strong>{plan.impact.affected_files.length}</strong><span>Files</span></div>
            <div><strong>{plan.impact.affected_endpoints.length}</strong><span>API routes</span></div>
            <div><strong>{plan.impact.dependency_depth}</strong><span>Max depth</span></div>
          </div>

          <button className="button subtle full" onClick={() => onShowEvidence(plan)}>
            <Network size={14} /> Highlight plan evidence
          </button>

          <div className="refactor-section-heading"><Workflow size={15} /><h3>Migration stages</h3></div>
          <div className="refactor-stages">
            {plan.stages.map((stage, index) => (
              <article key={`${stage.title}-${index}`}>
                <span className="stage-number">{index + 1}</span>
                <div className="stage-content">
                  <h4>{stage.title}</h4>
                  <p>{stage.objective}</p>
                  <ul>{stage.actions.map((action) => <li key={action}>{action}</li>)}</ul>
                  <div className="stage-evidence">
                    {stage.evidence_ids.map((id) => {
                      const node = evidence.get(id);
                      return node ? (
                        <button key={id} onClick={() => onOpenSource(node)} title={`${node.file_path}:${node.start_line}`}>
                          <FileCode2 size={11} />{node.name}
                        </button>
                      ) : null;
                    })}
                  </div>
                  <div className="stage-verification">
                    <strong><ListChecks size={13} />Verify</strong>
                    {stage.verification.map((item) => <span key={item}><Check size={11} />{item}</span>)}
                  </div>
                </div>
              </article>
            ))}
          </div>

          <div className="refactor-section-heading"><Check size={15} /><h3>Connected tests</h3></div>
          {plan.related_tests.length ? (
            <div className="refactor-tests">{plan.related_tests.map((path) => <code key={path}>{path}</code>)}</div>
          ) : (
            <div className="refactor-test-warning"><AlertTriangle size={15} /><span><strong>No connected tests found</strong><small>Add focused coverage before changing this symbol.</small></span></div>
          )}

          <div className="refactor-section-heading"><GitBranch size={15} /><h3>Affected files</h3></div>
          {plan.impact.affected_files.slice(0, 12).map((file) => <code className="refactor-file" key={file}>{file}</code>)}
          {plan.impact.affected_files.length > 12 && <p className="hint">And {plan.impact.affected_files.length - 12} more affected files.</p>}

          {(plan.impact.affected_endpoints.length > 0 || plan.impact.database_interactions.length > 0) && (
            <>
              <div className="refactor-section-heading"><Network size={15} /><h3>Routes and data</h3></div>
              <div className="refactor-surfaces">
                {[...plan.impact.affected_endpoints, ...plan.impact.database_interactions].map((id) => {
                  const node = graphNodes.get(id);
                  return node ? (
                    <button key={id} onClick={() => onOpenSource(node)}>
                      <span>{node.type}</span><strong>{node.name}</strong><small>{node.file_path || node.module}</small>
                    </button>
                  ) : null;
                })}
              </div>
            </>
          )}

          {plan.warning && <div className="refactor-provider-warning"><AlertTriangle size={14} />{plan.warning}</div>}
          <p className="hint">{plan.impact.caveat}</p>
        </>
      )}
    </div>
  );
}
