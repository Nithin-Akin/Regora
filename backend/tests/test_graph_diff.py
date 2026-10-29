from app.graph.diff import MAX_EVIDENCE, compare_graphs
from app.models.schema import CodeEdge, CodeGraph, CodeNode


def node(id, name, *, hash="one", type="Function", file="src/app.py", module="app"):
    return CodeNode(
        id=id,
        name=name,
        qualified_name=f"app:{name}",
        type=type,
        repository_id="repo",
        file_path=file,
        module=module,
        hash=hash,
    )


def test_graph_diff_reports_structural_changes_and_risk():
    stable_base = node("stable", "stable", hash="old")
    stable_head = node("stable", "stable", hash="new")
    removed = node("removed", "legacy")
    added = node("added", "orders", type="Endpoint", file="src/routes.py", module="routes")
    base = CodeGraph(
        nodes=[stable_base, removed],
        edges=[CodeEdge(id="old-call", source="stable", target="removed", type="CALLS")],
    )
    head = CodeGraph(
        nodes=[stable_head, added],
        edges=[CodeEdge(id="new-call", source="added", target="stable", type="CALLS")],
    )

    result = compare_graphs(base, head)

    assert result["summary"]["symbols"] == {"added": 1, "removed": 1, "modified": 1}
    assert result["summary"]["relationships"] == {"added": 1, "removed": 1, "modified": 0}
    assert result["summary"]["affected_endpoints"] == 1
    assert result["risk"]["score"] > 0
    assert {item["change"] for item in result["symbols"]} == {"added", "removed", "modified"}
    assert "embedding" not in result["symbols"][0]


def test_graph_diff_evidence_is_bounded():
    head = CodeGraph(nodes=[node(f"n-{index}", f"symbol_{index}") for index in range(MAX_EVIDENCE + 5)])
    result = compare_graphs(CodeGraph(), head)
    assert len(result["symbols"]) == MAX_EVIDENCE
    assert result["truncated"] is True


def test_equal_graphs_have_zero_risk():
    graph = CodeGraph(nodes=[node("same", "same")])
    result = compare_graphs(graph, graph)
    assert result["risk"] == {"score": 0, "level": "LOW"}
    assert result["symbols"] == []
