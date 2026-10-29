"""Deterministic, bounded comparisons between two repository graph snapshots."""

from app.models.schema import CodeEdge, CodeGraph, CodeNode

NODE_FIELDS = (
    "hash",
    "name",
    "type",
    "qualified_name",
    "file_path",
    "start_line",
    "end_line",
    "signature",
    "module",
    "exported",
    "parameters",
    "returns",
)
EDGE_FIELDS = ("source", "target", "type", "source_file", "source_line", "confidence", "resolution")
MAX_EVIDENCE = 200


def node_evidence(node: CodeNode, change: str, changed_fields: list[str] | None = None):
    return {
        "change": change,
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "qualified_name": node.qualified_name,
        "file_path": node.file_path,
        "start_line": node.start_line,
        "end_line": node.end_line,
        "signature": node.signature,
        **({"changed_fields": changed_fields} if changed_fields else {}),
    }


def edge_evidence(edge: CodeEdge, change: str, nodes: dict[str, CodeNode], changed_fields=None):
    source = nodes.get(edge.source)
    target = nodes.get(edge.target)
    return {
        "change": change,
        "id": edge.id,
        "type": edge.type,
        "source_id": edge.source,
        "source_name": source.qualified_name or source.name if source else edge.source,
        "target_id": edge.target,
        "target_name": target.qualified_name or target.name if target else edge.target,
        "source_file": edge.source_file,
        "source_line": edge.source_line,
        "resolution": edge.resolution,
        **({"changed_fields": changed_fields} if changed_fields else {}),
    }


def compare_graphs(base: CodeGraph, head: CodeGraph):
    base_nodes = {node.id: node for node in base.nodes}
    head_nodes = {node.id: node for node in head.nodes}
    added_ids = sorted(head_nodes.keys() - base_nodes.keys())
    removed_ids = sorted(base_nodes.keys() - head_nodes.keys())
    common_ids = sorted(base_nodes.keys() & head_nodes.keys())
    modified = [
        (
            head_nodes[node_id],
            [
                field
                for field in NODE_FIELDS
                if getattr(base_nodes[node_id], field) != getattr(head_nodes[node_id], field)
            ],
        )
        for node_id in common_ids
    ]
    modified = [(node, fields) for node, fields in modified if fields]

    base_edges = {edge.id: edge for edge in base.edges}
    head_edges = {edge.id: edge for edge in head.edges}
    added_edge_ids = sorted(head_edges.keys() - base_edges.keys())
    removed_edge_ids = sorted(base_edges.keys() - head_edges.keys())
    common_edge_ids = sorted(base_edges.keys() & head_edges.keys())
    modified_edges = [
        (
            head_edges[edge_id],
            [
                field
                for field in EDGE_FIELDS
                if getattr(base_edges[edge_id], field) != getattr(head_edges[edge_id], field)
            ],
        )
        for edge_id in common_edge_ids
    ]
    modified_edges = [(edge, fields) for edge, fields in modified_edges if fields]

    changed_nodes = [head_nodes[node_id] for node_id in added_ids]
    changed_nodes += [base_nodes[node_id] for node_id in removed_ids]
    changed_nodes += [node for node, _ in modified]
    changed_edges = [head_edges[edge_id] for edge_id in added_edge_ids]
    changed_edges += [base_edges[edge_id] for edge_id in removed_edge_ids]
    changed_edges += [edge for edge, _ in modified_edges]

    files = sorted(
        {node.file_path for node in changed_nodes if node.file_path}
        | {edge.source_file for edge in changed_edges if edge.source_file}
    )
    modules = sorted({node.module for node in changed_nodes if node.module})
    endpoints = sorted({node.qualified_name or node.name for node in changed_nodes if node.type == "Endpoint"})
    database_entities = sorted(
        {node.qualified_name or node.name for node in changed_nodes if node.type == "DatabaseEntity"}
    )

    changed_symbol_count = len(added_ids) + len(removed_ids) + len(modified)
    changed_relationship_count = len(added_edge_ids) + len(removed_edge_ids) + len(modified_edges)
    score = min(
        100,
        min(40, changed_symbol_count * 4)
        + min(20, changed_relationship_count * 2)
        + min(15, len(files) * 3)
        + min(10, len(endpoints) * 5)
        + min(10, len(database_entities) * 5)
        + min(5, len(removed_ids)),
    )
    risk = "HIGH" if score >= 60 else "MEDIUM" if score >= 25 else "LOW"
    all_nodes = base_nodes | head_nodes

    symbol_evidence = [node_evidence(head_nodes[node_id], "added") for node_id in added_ids]
    symbol_evidence += [node_evidence(base_nodes[node_id], "removed") for node_id in removed_ids]
    symbol_evidence += [node_evidence(node, "modified", fields) for node, fields in modified]
    relationship_evidence = [edge_evidence(head_edges[edge_id], "added", all_nodes) for edge_id in added_edge_ids]
    relationship_evidence += [edge_evidence(base_edges[edge_id], "removed", all_nodes) for edge_id in removed_edge_ids]
    relationship_evidence += [edge_evidence(edge, "modified", all_nodes, fields) for edge, fields in modified_edges]

    return {
        "summary": {
            "symbols": {"added": len(added_ids), "removed": len(removed_ids), "modified": len(modified)},
            "relationships": {
                "added": len(added_edge_ids),
                "removed": len(removed_edge_ids),
                "modified": len(modified_edges),
            },
            "affected_files": len(files),
            "affected_modules": len(modules),
            "affected_endpoints": len(endpoints),
            "affected_database_entities": len(database_entities),
        },
        "risk": {"score": score, "level": risk},
        "affected": {
            "files": files,
            "modules": modules,
            "endpoints": endpoints,
            "database_entities": database_entities,
        },
        "symbols": symbol_evidence[:MAX_EVIDENCE],
        "relationships": relationship_evidence[:MAX_EVIDENCE],
        "truncated": len(symbol_evidence) > MAX_EVIDENCE or len(relationship_evidence) > MAX_EVIDENCE,
        "limitations": "Static graph comparison cannot observe runtime-only calls, reflection, or dynamic configuration.",
    }
