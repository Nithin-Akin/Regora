"""Bounded, deterministic graph algorithms over the graph persisted in Neo4j."""

from collections import Counter, defaultdict
from functools import lru_cache
import networkx as nx
from app.models.schema import CodeGraph, stable_id

DEPENDENCY_TYPES = {
    "CALLS",
    "IMPORTS",
    "REFERENCES",
    "EXTENDS",
    "IMPLEMENTS",
    "HANDLES",
    "ROUTES_TO",
    "DEPENDS_ON",
    "USES_PACKAGE",
    "READS_FROM",
    "WRITES_TO",
}


class Intelligence:
    def __init__(self, graph: CodeGraph):
        self.graph = graph
        self.nodes = {n.id: n for n in graph.nodes}
        self.net = nx.DiGraph()
        self.net.add_nodes_from(self.nodes)
        for edge in graph.edges:
            if edge.type in DEPENDENCY_TYPES and edge.resolution != "unresolved":
                self.net.add_edge(edge.source, edge.target)

    def public_node(self, id):
        return self.nodes[id].model_dump(exclude={"embedding", "source"})

    def subgraph(self, ids, limit=250):
        ids = list(dict.fromkeys(i for i in ids if i in self.nodes))
        total = len(ids)
        selected = set(ids[:limit])
        return {
            "nodes": [self.public_node(i) for i in ids[:limit]],
            "edges": [e.model_dump() for e in self.graph.edges if e.source in selected and e.target in selected],
            "truncated": total > limit,
            "total": total,
        }

    def neighbors(self, id, depth=1, types=None, direction="both", limit=250):
        if id not in self.nodes:
            raise KeyError(id)
        selected, frontier = {id}, {id}
        for _ in range(min(5, max(0, depth))):
            added = set()
            for e in self.graph.edges:
                if types and e.type not in types:
                    continue
                if direction in {"both", "out"} and e.source in frontier:
                    added.add(e.target)
                if direction in {"both", "in"} and e.target in frontier:
                    added.add(e.source)
            frontier = added - selected
            selected |= added
            if len(selected) >= limit:
                break
        return self.subgraph([id] + sorted(selected - {id}), limit)

    @lru_cache(maxsize=256)
    def path(self, source, target, directed=True):
        try:
            path = nx.shortest_path(self.net if directed else self.net.to_undirected(), source, target)
            return path if len(path) <= 16 else []
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def trace(self, id):
        if id not in self.nodes:
            raise KeyError(id)
        paths = []
        visited = nx.single_source_shortest_path(self.net, id, cutoff=8)
        for target, path in visited.items():
            if self.nodes[target].type in {"DatabaseEntity", "ExternalPackage"} or (
                len(path) > 1 and self.net.out_degree(target) == 0
            ):
                paths.append(path)
        return {"paths": sorted(paths, key=len, reverse=True)[:25], "graph": self.subgraph(visited), "max_depth": 8}

    @lru_cache(maxsize=64)
    def impact(self, id):
        if id not in self.nodes:
            raise KeyError(id)
        selected = {id}
        # Changes to a class/file can affect each defined member.
        if self.nodes[id].type in {"File", "Class", "Interface"}:
            frontier = {id}
            for _ in range(3):
                frontier = {
                    e.target for e in self.graph.edges if e.source in frontier and e.type in {"DEFINES", "CONTAINS"}
                }
                selected |= frontier
        reverse = self.net.reverse(copy=False)
        paths = {}
        for seed in selected:
            for target, path in nx.single_source_shortest_path(reverse, seed, cutoff=8).items():
                if target not in paths or len(path) < len(paths[target]):
                    paths[target] = path
        dependents = set(paths) - selected
        direct = {p for s in selected for p in self.net.predecessors(s)} - selected
        endpoints = [i for i in dependents if self.nodes[i].type == "Endpoint"]
        files = sorted({self.nodes[i].file_path for i in dependents if self.nodes[i].file_path})
        modules = sorted({self.nodes[i].module for i in dependents if self.nodes[i].module})
        affected = dependents | selected
        db = {e.target for e in self.graph.edges if e.source in affected and e.type in {"READS_FROM", "WRITES_TO"}}
        writes = {e.target for e in self.graph.edges if e.source in affected and e.type == "WRITES_TO"}
        depth = max((len(p) - 1 for p in paths.values()), default=0)
        features = {
            "direct_dependents": min(20, len(direct) * 4),
            "transitive_dependents": min(25, len(dependents - direct) * 2),
            "api_endpoints": min(20, len(endpoints) * 5),
            "cross_module_reach": min(15, max(0, len(modules) - 1) * 3),
            "database_writes": min(10, len(writes) * 5),
            "dependency_depth": min(10, depth * 2),
        }
        score = sum(features.values())
        return {
            "symbol_id": id,
            "score": score,
            "risk": "HIGH" if score >= 65 else "MEDIUM" if score >= 30 else "LOW",
            "features": features,
            "direct_callers": sorted(
                {
                    e.source
                    for e in self.graph.edges
                    if e.target in selected and e.type == "CALLS" and e.resolution != "unresolved"
                }
                - selected
            ),
            "direct_dependents": sorted(direct),
            "indirect_callers": sorted(dependents - direct),
            "affected_files": files,
            "affected_modules": modules,
            "affected_endpoints": endpoints,
            "database_interactions": sorted(db),
            "dependency_depth": depth,
            "blast_radius": len(dependents),
            "paths": [list(reversed(p)) for p in sorted(paths.values(), key=len, reverse=True)[:12]],
            "graph": self.subgraph([id] + sorted(affected - {id}) + sorted(db)),
            "caveat": "Potential impact from static dependencies, capped at 8 hops. Dynamic dispatch and runtime configuration may add dependencies.",
        }

    @lru_cache(maxsize=8)
    def overview(self):
        counts = Counter(n.type for n in self.graph.nodes)
        files = [n for n in self.graph.nodes if n.type == "File"]
        centrality = sorted(self.net.degree, key=lambda pair: pair[1], reverse=True)[:10]
        cycles = []
        # SCC detection is linear; avoid exponential enumeration of all simple cycles.
        for component in nx.strongly_connected_components(self.net):
            if len(component) > 1 or (
                len(component) == 1 and self.net.has_edge(next(iter(component)), next(iter(component)))
            ):
                found = nx.find_cycle(self.net.subgraph(component))
                cycles.append([a for a, b in found] + [found[0][0]])
                if len(cycles) == 20:
                    break
        unreferenced = [
            n.id
            for n in self.graph.nodes
            if n.type in {"Function", "Method"}
            and self.net.in_degree(n.id) == 0
            and not n.name.startswith(("__", "callback@"))
        ]
        return {
            "counts": dict(counts),
            "files": len(files),
            "lines": sum(n.end_line for n in files),
            "nodes": len(self.graph.nodes),
            "relationships": len(self.graph.edges),
            "languages": dict(Counter(n.language for n in files)),
            "largest_modules": dict(Counter(n.module for n in files).most_common(10)),
            "hubs": [{"node": self.public_node(id), "degree": degree} for id, degree in centrality],
            "cycles": cycles,
            "potentially_unused": unreferenced[:50],
            "unresolved_relationships": sum(e.resolution == "unresolved" for e in self.graph.edges),
        }

    @lru_cache(maxsize=8)
    def architecture(self):
        # Aggregation derives solely from file paths and existing dependency edges.
        group = {}
        groups = defaultdict(list)
        for n in self.graph.nodes:
            if n.type in {"Repository", "Directory", "UnresolvedSymbol"}:
                continue
            key = (
                "External packages"
                if n.type == "ExternalPackage"
                else "Database"
                if n.type == "DatabaseEntity"
                else n.module or "root"
            )
            group[n.id] = key
            groups[key].append(n.id)
        r = next(iter(self.nodes.values())).repository_id if self.nodes else ""
        aggregates = [
            dict(
                id=stable_id(r, "architecture", name),
                name=name,
                type="Component",
                repository_id=r,
                members=ids,
                count=len(ids),
                module=name,
                file_path="",
                start_line=1,
                end_line=1,
            )
            for name, ids in groups.items()
        ]
        ids = {n["name"]: n["id"] for n in aggregates}
        relationships = defaultdict(list)
        for e in self.graph.edges:
            if (
                e.type in DEPENDENCY_TYPES
                and e.resolution != "unresolved"
                and e.source in group
                and e.target in group
                and group[e.source] != group[e.target]
            ):
                relationships[(group[e.source], group[e.target])].append(e)
        result = []
        for (a, b), evidence in relationships.items():
            result.append(
                dict(
                    id=stable_id(ids[a], ids[b]),
                    source=ids[a],
                    target=ids[b],
                    type="DEPENDS_ON",
                    count=len(evidence),
                    evidence=[e.model_dump() for e in evidence[:20]],
                    resolution="resolved" if all(e.resolution == "resolved" for e in evidence) else "probable",
                )
            )
        return {
            "nodes": aggregates[:100],
            "edges": [
                e
                for e in result
                if e["source"] in {n["id"] for n in aggregates[:100]}
                and e["target"] in {n["id"] for n in aggregates[:100]}
            ],
            "truncated": len(aggregates) > 100,
            "total": len(aggregates),
        }
