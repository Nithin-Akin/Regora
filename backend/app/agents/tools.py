from app.retrieval.hybrid import HybridRetrieval

TOOL_SPECS = {
    "semantic_search": ("Find code by meaning", {"query": "string"}),
    "search_symbol": ("Find exact symbols by name", {"name": "string"}),
    "get_symbol": ("Inspect a known symbol and its relationships", {"symbol_id": "string"}),
    "get_source": ("Read source code for a symbol", {"symbol_id": "string"}),
    "find_callers": ("Get incoming CALLS edges", {"symbol_id": "string"}),
    "find_callees": ("Get outgoing CALLS edges", {"symbol_id": "string"}),
    "get_neighbors": ("Expand the graph, up to 3 hops", {"symbol_id": "string", "depth": "integer"}),
    "shortest_path": ("Find a directed dependency path", {"source_id": "string", "target_id": "string"}),
    "trace_endpoint": ("Trace a route toward persistence and external dependencies", {"endpoint_id": "string"}),
    "analyze_impact": ("Calculate potential blast radius and explainable risk", {"symbol_id": "string"}),
    "repository_overview": ("Get architecture metrics, hubs, and cycles", {}),
    "search_code": ("Find literal source text", {"query": "string"}),
    "get_dependencies": ("Get dependencies of a symbol", {"symbol_id": "string"}),
    "get_dependents": ("Get dependents of a symbol", {"symbol_id": "string"}),
}


def schemas():
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {key: {"type": kind} for key, kind in properties.items()},
                    "required": list(properties),
                    "additionalProperties": False,
                },
            },
        }
        for name, (description, properties) in TOOL_SPECS.items()
    ]


class AgentTools:
    def __init__(self, intelligence, store):
        self.i = intelligence
        self.search = HybridRetrieval(intelligence, store)
        self.seen = set()
        self.edge_ids = set()
        self.calls = []

    def execute(self, name, args):
        if name not in TOOL_SPECS:
            raise ValueError("Unknown tool")
        expected = TOOL_SPECS[name][1]
        if set(args) != set(expected):
            raise ValueError("Invalid tool arguments")
        for key, kind in expected.items():
            value = args[key]
            if kind == "string" and (not isinstance(value, str) or len(value) > 4000):
                raise ValueError("Invalid string argument")
            if kind == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                raise ValueError("Invalid integer argument")
            if key.endswith("_id") and value not in self.i.nodes:
                raise ValueError("Symbol is not in this repository")
        id = args.get("symbol_id")
        if name in {"semantic_search", "search_symbol", "search_code"}:
            result = self.search.search(
                args.get("query", args.get("name", "")),
                {"semantic_search": "hybrid", "search_symbol": "symbol", "search_code": "text"}[name],
                8,
            )
        elif name == "repository_overview":
            result = self.i.overview()
        elif name in {"get_source", "get_symbol"}:
            result = {
                "node": self.i.nodes[id].model_dump(exclude={"embedding"}),
                "graph": self.i.neighbors(id, 1, limit=30),
            }
            result["node"]["source"] = result["node"]["source"][:6000]
        elif name == "shortest_path":
            path = self.i.path(args["source_id"], args["target_id"])
            result = {"paths": [path] if path else [], "graph": self.i.subgraph(path)}
        elif name == "trace_endpoint":
            result = self.i.trace(args["endpoint_id"])
        elif name in {"analyze_impact", "get_dependents"}:
            result = self.i.impact(id)
        else:
            types = ["CALLS"] if name in {"find_callers", "find_callees"} else None
            direction = (
                "in"
                if name in {"find_callers", "get_dependents"}
                else "out"
                if name in {"find_callees", "get_dependencies"}
                else "both"
            )
            result = self.i.neighbors(
                id, min(3, args.get("depth", 3 if name == "get_dependencies" else 1)), types, direction, 50
            )
        self.calls.append({"name": name, "arguments": args})
        return result

    def record_evidence(self, value):
        if isinstance(value, dict):
            id = value.get("id")
            if id in self.i.nodes:
                self.seen.add(id)
            if "source" in value and "target" in value and "id" in value:
                self.edge_ids.add(value["id"])
            for v in value.values():
                self.record_evidence(v)
        elif isinstance(value, list):
            for v in value:
                self.record_evidence(v)
