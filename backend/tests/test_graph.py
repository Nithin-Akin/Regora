from conftest import symbol
from app.graph.intelligence import Intelligence


def test_every_edge_has_nodes_and_provenance(demo_graph):
    ids = {n.id for n in demo_graph.nodes}
    assert len(ids) == len(demo_graph.nodes)
    for edge in demo_graph.edges:
        assert edge.source in ids and edge.target in ids
        assert edge.source_file and edge.source_line >= 1 and edge.analysis_method


def test_checkout_reaches_payment_and_database(demo_graph, demo_intelligence):
    endpoint = symbol(demo_graph, "POST /checkout")
    payment = symbol(demo_graph, "PaymentService.process_payment")
    path = demo_intelligence.path(endpoint.id, payment.id)
    assert len(path) == 4
    entity = next(n for n in demo_graph.nodes if n.type == "DatabaseEntity" and n.name == "Order")
    path = demo_intelligence.path(endpoint.id, entity.id)
    assert len(path) == 4


def test_auth_impact_reaches_protected_routes(demo_graph, demo_intelligence):
    token = symbol(demo_graph, "verify_token")
    impact = demo_intelligence.impact(token.id)
    names = {demo_intelligence.nodes[id].name for id in impact["affected_endpoints"]}
    assert {"GET /profile", "POST /checkout", "GET /orders"} <= names
    assert impact["score"] == sum(impact["features"].values())
    assert 0 <= impact["score"] <= 100


def test_class_impact_includes_member_callers(demo_graph, demo_intelligence):
    result = demo_intelligence.impact(symbol(demo_graph, "PaymentService").id)
    assert "api/routes.py" in result["affected_files"]
    assert result["affected_endpoints"]


def test_cycles_and_architecture_have_evidence(demo_intelligence):
    assert demo_intelligence.overview()["cycles"]
    architecture = demo_intelligence.architecture()
    assert architecture["nodes"]
    assert all(edge["evidence"] for edge in architecture["edges"])


def test_unresolved_not_in_dependency_traversal(parse):
    graph = parse({"app.py": "def caller():\n    unknown()\n"})
    i = Intelligence(graph)
    unresolved = next(n for n in graph.nodes if n.type == "UnresolvedSymbol")
    assert i.net.degree(unresolved.id) == 0


def test_neighbors_bounded(demo_graph, demo_intelligence):
    node = symbol(demo_graph, "checkout", "api/routes.py")
    result = demo_intelligence.neighbors(node.id, 5, limit=7)
    assert len(result["nodes"]) <= 7
    assert all(
        e["source"] in {n["id"] for n in result["nodes"]} and e["target"] in {n["id"] for n in result["nodes"]}
        for e in result["edges"]
    )
