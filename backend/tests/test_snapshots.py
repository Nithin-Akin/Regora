from app.graph.snapshots import decode_graph_snapshot, encode_graph_snapshot
from app.models.schema import CodeEdge, CodeGraph, CodeNode


def sample_graph():
    return CodeGraph(
        nodes=[
            CodeNode(
                id="node-1",
                name="checkout",
                type="Function",
                repository_id="repo-1",
                qualified_name="shop.checkout",
                file_path="shop.py",
                hash="hash-1",
                embedding=[0.1, 0.2, 0.3],
            )
        ],
        edges=[CodeEdge(id="edge-1", source="node-1", target="node-1", type="CALLS")],
        fingerprint="fingerprint-1",
    )


def test_snapshot_round_trip_excludes_embeddings_without_mutating_graph():
    graph = sample_graph()

    restored = decode_graph_snapshot(encode_graph_snapshot(graph))

    assert restored.fingerprint == "fingerprint-1"
    assert restored.nodes[0].name == "checkout"
    assert restored.nodes[0].embedding == []
    assert graph.nodes[0].embedding == [0.1, 0.2, 0.3]


def test_invalid_snapshot_is_rejected():
    try:
        decode_graph_snapshot("not-base64")
    except ValueError as exc:
        assert str(exc) == "Stored graph snapshot is invalid"
    else:
        raise AssertionError("Invalid snapshot should fail")
