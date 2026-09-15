from pathlib import Path
import pytest
from app.parsers.pipeline import analyze_repository
from app.graph.intelligence import Intelligence


@pytest.fixture
def parse(tmp_path):
    def build(files):
        for name, source in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        return analyze_repository(tmp_path, "test")

    return build


@pytest.fixture(scope="session")
def demo_graph():
    return analyze_repository(Path(__file__).parents[2] / "demo/shop", "demo-test")


@pytest.fixture(scope="session")
def demo_intelligence(demo_graph):
    return Intelligence(demo_graph)


def symbol(graph, name, path=None):
    return next(
        n
        for n in graph.nodes
        if (n.name == name or n.qualified_name.endswith(":" + name))
        and (not path or n.file_path == path)
        and n.type != "UnresolvedSymbol"
    )


def triples(graph, kind="CALLS"):
    nodes = {n.id: n for n in graph.nodes}
    return {
        (nodes[e.source].qualified_name, nodes[e.target].qualified_name)
        for e in graph.edges
        if e.type == kind and e.resolution == "resolved"
    }
