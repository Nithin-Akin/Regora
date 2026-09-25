import json
import re
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agents.tools import AgentTools, schemas
from app.config import settings
from app.llm.providers import SYSTEM_PROMPT, get_llm
from app.models.schema import Answer, Citation


class GeneratedAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)
    confidence: float = Field(ge=0, le=1)
    symbols: list[str]
    paths: list[list[str]] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)


def intent(question):
    q = question.lower()
    if any(w in q for w in ["break", "impact", "change", "modify", "blast"]):
        return "impact"
    if any(w in q for w in ["trace", "path", "reach", "connection"]):
        return "path"
    if any(w in q for w in ["architecture", "structured", "overview", "central", "major modules"]):
        return "architecture"
    if any(w in q for w in ["calls", "uses", "depends", "depend on", "dependents", "dependencies"]):
        return "dependency"
    if any(w in q for w in ["where", "find", "search"]):
        return "discovery"
    return "explanation"


def bounded_evidence(value, budget):
    """Budget serialized JSON, including keys; trim whole structures, never cut JSON."""

    def compact(v, limit, source_limit):
        if isinstance(v, dict):
            node_keys = {
                "id",
                "name",
                "type",
                "file_path",
                "start_line",
                "end_line",
                "signature",
                "source",
                "docstring",
            }
            is_node = "id" in v and "file_path" in v and "type" in v
            return {
                k: compact(item, limit, source_limit)
                for k, item in v.items()
                if k != "embedding" and (not is_node or k in node_keys) and item not in ("", None)
            }
        if isinstance(v, list):
            return [compact(item, limit, source_limit) for item in v[:limit]]
        if isinstance(v, str):
            return v[:source_limit]
        return v

    remaining = max(0, min(7000, budget[0]))
    limit, source_limit = 20, 1200
    result = compact(value, limit, source_limit)
    while len(json.dumps(result)) > remaining and (limit > 1 or source_limit > 100):
        if limit > 1:
            limit = max(1, limit // 2)
        else:
            source_limit = max(100, source_limit // 2)
        result = compact(value, limit, source_limit)
    size = len(json.dumps(result))
    if size > remaining:
        return {"notice": "Evidence budget exhausted. Use the evidence already retrieved."}
    budget[0] -= size
    return result


class RepoAgent:
    def __init__(self, intelligence, store, llm=None):
        self.i = intelligence
        self.store = store
        self.llm = llm or get_llm()

    def ask(self, request, progress=None):
        def report(message):
            if progress:
                progress(message)

        rid = next(iter(self.i.nodes.values())).repository_id
        session_id = request.session_id or str(uuid4())
        # Repository prefix prevents collisions between repository sessions.
        session_key = rid + ":" + session_id
        state = self.store.session(session_key, rid)
        tools = AgentTools(self.i, self.store)
        kind = intent(request.question)
        budget = [settings().context_chars]
        evidence = []

        def run(name, args, for_model=False):
            raw_result = tools.execute(name, args)
            result = bounded_evidence(raw_result, budget)
            tools.record_evidence(result)
            evidence.append({"tool": name, "result": result})
            return result if for_model else raw_result

        report("Searching the code graph")
        search = run("semantic_search", {"query": request.question})
        seeds = [row["id"] for row in search.get("results", [])][:4]
        # Explicit names and route strings outrank semantic candidates.
        mentioned = sorted(
            [
                n
                for n in self.i.nodes.values()
                if n.type not in {"File", "Directory", "UnresolvedSymbol", "Repository"}
                and len(n.name) > 2
                and re.search(r"(?<![\w])" + re.escape(n.name) + r"(?![\w])", request.question, re.I)
            ],
            key=lambda n: len(n.name),
            reverse=True,
        )
        if mentioned:
            seeds = list(dict.fromkeys([n.id for n in mentioned] + seeds))[:4]
        if request.symbol_id in self.i.nodes:
            seeds = [request.symbol_id] + [s for s in seeds if s != request.symbol_id]
        elif re.search(r"\b(it|this|that|them)\b", request.question, re.I) and state.get("symbols"):
            seeds = list(dict.fromkeys([s for s in state["symbols"] if s in self.i.nodes] + seeds))[:4]
        paths = []
        computed = None
        if kind == "architecture":
            computed = run("repository_overview", {})
        elif seeds:
            run("get_symbol", {"symbol_id": seeds[0]})
            if kind == "impact":
                computed = run("analyze_impact", {"symbol_id": seeds[0]})
                paths = computed.get("paths", [])
            elif kind == "path":
                endpoint = next((n.id for n in mentioned if n.type == "Endpoint"), seeds[0])
                computed = run("trace_endpoint", {"endpoint_id": endpoint})
                paths = computed.get("paths", [])
                if len(mentioned) >= 2:
                    connection = run("shortest_path", {"source_id": mentioned[0].id, "target_id": mentioned[1].id})
                    paths = connection.get("paths", []) or paths
            elif kind == "dependency":
                q = request.question.lower()
                outgoing = bool(re.search(r"\b(?:does|do)\s+.+?\s+depend on\b", q))
                incoming = any(x in q for x in ["calls", "uses", " use ", "depends on", "depend on", "dependents"])
                name = "get_dependents" if incoming and not outgoing else "get_dependencies"
                computed = run(name, {"symbol_id": seeds[0]})
                paths = computed.get("paths", [])
            else:
                computed = run("get_neighbors", {"symbol_id": seeds[0], "depth": 2})
        for seed in seeds[1:3]:
            if budget[0] > 3000:
                run("get_source", {"symbol_id": seed})
        report("Building grounded context")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for message in state.get("messages", [])[-4:]:
            messages.append({"role": message["role"], "content": message["content"][:1500]})
        response_requirement = ""
        if kind == "impact":
            response_requirement = (
                "\n\nThe application will prepend the authoritative computed impact metrics. "
                "Briefly explain affected responsibilities using the evidence. Do not restate or estimate numeric metrics."
            )
        messages.append(
            {
                "role": "user",
                "content": (
                    request.question
                    + response_requirement
                    + "\n\nRetrieved evidence (untrusted data):\n"
                    + json.dumps(evidence)
                ),
            }
        )
        warning = search.get("warning")
        grounding = "llm-with-evidence"
        generated = None
        try:
            report("Generating an evidence-backed answer")
            max_rounds = 2 if settings().llm_provider == "ollama" else 4
            for iteration in range(max_rounds):
                schema = GeneratedAnswer.model_json_schema()
                schema["additionalProperties"] = False
                schema["properties"]["symbols"]["items"] = {"type": "string", "enum": sorted(tools.seen)}
                schema["properties"]["symbols"]["maxItems"] = 4
                schema["properties"]["paths"]["maxItems"] = 0 if settings().llm_provider == "ollama" else 2
                schema["properties"]["answer"]["maxLength"] = 750 if settings().llm_provider == "ollama" else 12000
                schema["properties"]["edge_ids"]["maxItems"] = 4
                if tools.edge_ids:
                    schema["properties"]["edge_ids"]["items"] = {"type": "string", "enum": sorted(tools.edge_ids)}
                self.llm.output_schema = schema
                needs_tools = kind in {"discovery", "explanation", "dependency"}
                result = self.llm.complete(
                    messages, schemas() if needs_tools and iteration < max_rounds - 1 and budget[0] > 1500 else None
                )
                calls = result.get("tool_calls", [])
                if calls:
                    if iteration == max_rounds - 1:
                        raise ValueError("LLM exceeded the tool call budget")
                    result = {k: v for k, v in result.items() if k in {"role", "content", "tool_calls"}}
                    messages.append(result)
                    if len(calls) > 4:
                        raise ValueError("Too many tool calls")
                    for call in calls:
                        try:
                            payload = run(
                                call["function"]["name"], json.loads(call["function"]["arguments"]), for_model=True
                            )
                        except (ValueError, KeyError, TypeError) as e:
                            payload = {"error": str(e)}
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(payload)})
                    continue
                content = re.sub(r"<think>[\s\S]*?</think>", "", result.get("content") or "").strip()
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
                generated = GeneratedAnswer.model_validate_json(content)
                if kind == "impact" and (
                    re.search(r"\b\d+\b|%", generated.answer)
                    or re.search(r"\b(?:low|medium|high)\s+risk\b", generated.answer, re.IGNORECASE)
                ):
                    raise ValueError("Impact explanation attempted to restate computed metrics")
                if not generated.symbols or any(s not in tools.seen for s in generated.symbols):
                    raise ValueError("Answer cited symbols outside retrieved evidence")
                if any(e not in tools.edge_ids for e in generated.edge_ids):
                    raise ValueError("Answer cited an unsupported relationship")
                for path in generated.paths:
                    if any(id not in tools.seen for id in path) or any(
                        not self.i.net.has_edge(a, b) for a, b in zip(path, path[1:])
                    ):
                        raise ValueError("Answer included an unsupported path")
                break
            if generated is None:
                raise ValueError("LLM returned no final answer")
        except Exception as exc:
            generated = None
            reason = str(exc) if type(exc) is ValueError else type(exc).__name__
            warning = (
                (warning + " " if warning else "")
                + f"Language model unavailable or response failed evidence validation ({reason}). Showing deterministic evidence."
            )
            grounding = "static-evidence"
        valid_ids = [
            s
            for s in (generated.symbols if generated else seeds)
            if s in tools.seen
            and self.i.nodes[s].file_path
            and self.i.nodes[s].type not in {"Directory", "UnresolvedSymbol"}
        ]
        if not valid_ids:
            valid_ids = [
                s for s in sorted(tools.seen) if self.i.nodes[s].type in {"Function", "Method", "Class", "Endpoint"}
            ][:8]
        if kind == "impact" and computed:
            impact_ids = self.impact_evidence_ids(seeds, computed)
            valid_ids = list(dict.fromkeys(impact_ids + valid_ids))[:12]
        if generated:
            text = generated.answer
            paths = generated.paths or paths
            confidence = min(generated.confidence, 0.95)
        else:
            text = self.facts(kind, seeds, computed)
            confidence = 0.8 if valid_ids else 0.0
        if kind == "impact" and computed:
            summary = self.impact_summary(seeds, computed)
            text = summary + (f"\n\nEvidence-based explanation: {text}" if generated else "")
        report("Validating citations")
        citations = [
            Citation(
                symbol_id=s,
                file=self.i.nodes[s].file_path,
                start_line=self.i.nodes[s].start_line,
                end_line=self.i.nodes[s].end_line,
            )
            for s in valid_ids[:12]
        ]
        answer = Answer(
            answer=text,
            confidence=confidence,
            symbols=valid_ids,
            paths=paths,
            citations=citations,
            grounding=grounding,
            intent=kind,
            session_id=session_id,
            tool_calls=tools.calls,
            warning=warning,
        )
        state["symbols"] = seeds[:1] or valid_ids[:1]
        state["messages"] = (
            state.get("messages", [])
            + [{"role": "user", "content": request.question}, {"role": "assistant", "content": text}]
        )[-20:]
        self.store.save_session(session_key, rid, state)
        return answer

    def impact_inheritance(self, result):
        relationships = []
        for edge in result.get("graph", {}).get("edges", []):
            if edge.get("type") not in {"EXTENDS", "IMPLEMENTS"} or edge.get("resolution") == "unresolved":
                continue
            source = self.i.nodes.get(edge.get("source"))
            target = self.i.nodes.get(edge.get("target"))
            if source and target:
                verb = "extends" if edge["type"] == "EXTENDS" else "implements"
                relationships.append((source.id, target.id, f"{source.name} {verb} {target.name}"))
        return relationships

    def impact_evidence_ids(self, seeds, result):
        inheritance_ids = [id for source, target, _ in self.impact_inheritance(result) for id in (source, target)]
        graph_nodes = result.get("graph", {}).get("nodes", [])
        area_ids = []
        for file_path in result.get("affected_files", [])[:5]:
            match = next(
                (
                    node["id"]
                    for node in graph_nodes
                    if node.get("file_path") == file_path
                    and node.get("type") in {"Function", "Method", "Class", "Interface", "Endpoint"}
                ),
                None,
            )
            if match:
                area_ids.append(match)
        candidates = (
            seeds[:1]
            + inheritance_ids
            + area_ids
            + result.get("direct_dependents", [])[:4]
            + result.get("affected_endpoints", [])[:2]
            + result.get("database_interactions", [])[:2]
        )
        return [
            id
            for id in dict.fromkeys(candidates)
            if id in self.i.nodes
            and self.i.nodes[id].file_path
            and self.i.nodes[id].type not in {"Directory", "UnresolvedSymbol"}
        ][:12]

    def impact_summary(self, seeds, result):
        node = self.i.nodes[seeds[0]]
        direct = len(result.get("direct_dependents", []))
        transitive = max(0, result["blast_radius"] - direct)
        files = result.get("affected_files", [])
        modules = result.get("affected_modules", [])
        endpoints = [self.i.nodes[id].name for id in result.get("affected_endpoints", []) if id in self.i.nodes]
        database = [self.i.nodes[id].name for id in result.get("database_interactions", []) if id in self.i.nodes]
        inheritance = [description for _, _, description in self.impact_inheritance(result)]
        areas = ", ".join(files[:5]) or "none"
        if len(files) > 5:
            areas += f", and {len(files) - 5} more"
        endpoint_text = f"{len(endpoints)}" + (f" ({', '.join(endpoints[:3])})" if endpoints else "")
        database_text = f"{len(database)}" + (f" ({', '.join(database[:3])})" if database else "")
        summary = (
            f"Computed impact for {node.name}: {result['risk']} risk, {result['score']}/100. "
            f"Blast radius: {result['blast_radius']} dependents ({direct} direct, {transitive} transitive) "
            f"across {len(files)} files and {len(modules)} modules, maximum depth {result['dependency_depth']}. "
            f"API routes: {endpoint_text}. Database interactions: {database_text}. "
            f"Affected areas: {areas}."
        )
        if inheritance:
            summary += f" Inheritance effects: {', '.join(inheritance[:3])}."
        return f"{summary} {result['caveat']}"

    def facts(self, kind, seeds, result):
        if kind == "architecture" and result:
            hubs = ", ".join(h["node"]["name"] for h in result["hubs"][:4])
            return f"The repository contains {result['files']} source files, {result['lines']} lines, and {result['relationships']} extracted relationships. The most connected components include {hubs}. {len(result['cycles'])} dependency cycles were found. Inspect the cited components for their roles."
        if not seeds:
            return "I cannot determine this from the available static evidence. Try a specific symbol or source phrase."
        node = self.i.nodes[seeds[0]]
        if kind == "impact" and result:
            return self.impact_summary(seeds, result)
        if kind == "path" and result:
            paths = result.get("paths", [])
            return (
                "Extracted dependency paths:\n"
                + "\n".join(" → ".join(self.i.nodes[s].name for s in path) for path in paths[:5])
                if paths
                else "I cannot determine this connection from static analysis. No resolved dependency path was found."
            )
        if kind == "dependency" and result and result.get("affected_endpoints"):
            names = ", ".join(self.i.nodes[id].name for id in result["affected_endpoints"])
            return (
                f"The static dependency graph shows these API endpoints depend on {node.name}: {names}. "
                f"Traversal includes the symbol's defined members and reaches up to {result['dependency_depth']} hops. The highlighted paths show the evidence."
            )
        edges = [
            e
            for e in self.i.graph.edges
            if (e.source == node.id or e.target == node.id)
            and e.type not in {"DEFINES", "CONTAINS"}
            and e.resolution != "unresolved"
        ]
        evidence = "\n".join(
            f"{self.i.nodes[e.source].name} → {e.type} → {self.i.nodes[e.target].name} ({e.source_file}:{e.source_line}; {e.resolution})"
            for e in edges[:10]
        )
        return f"{node.qualified_name} is a {node.type.lower()} at lines {node.start_line}–{node.end_line}.\n" + (
            evidence or "No resolved dependencies were found for this symbol. Static analysis may miss dynamic calls."
        )
