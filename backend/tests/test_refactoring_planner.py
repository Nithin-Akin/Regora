import json

from conftest import symbol

from app.agents.refactoring import RefactoringPlanner


class Unavailable:
    def complete(self, *args):
        raise ConnectionError("offline")


def generated_payload(target_id, evidence_id=None):
    evidence_id = evidence_id or target_id
    return {
        "summary": "Move the selected responsibility behind a stable contract and migrate connected callers.",
        "confidence": 0.88,
        "stages": [
            {
                "title": "Define the contract",
                "objective": "Document the behavior that callers rely on.",
                "actions": ["Review the selected symbol and preserve its externally used behavior."],
                "evidence_ids": [target_id],
                "verification": ["Confirm the current callers are represented in the impact graph."],
            },
            {
                "title": "Migrate callers",
                "objective": "Update connected code in a controlled sequence.",
                "actions": ["Change the implementation and then update graph dependents."],
                "evidence_ids": [evidence_id],
                "verification": ["Reindex and verify the dependency paths."],
            },
        ],
    }


def test_refactoring_plan_uses_validated_model_stages(demo_graph, demo_intelligence):
    target = symbol(demo_graph, "PaymentService")

    class GroundedLLM:
        def complete(self, messages):
            assert "computed_impact" in messages[-1]["content"]
            return {"content": json.dumps(generated_payload(target.id))}

    result = RefactoringPlanner(demo_intelligence, GroundedLLM()).plan(
        target.id, "Extract payment provider selection behind an interface"
    )

    assert result["grounding"] == "llm-with-evidence"
    assert result["confidence"] == 0.88
    assert result["impact"]["score"] == demo_intelligence.impact(target.id)["score"]
    assert result["stages"][0]["evidence_ids"] == [target.id]
    assert {citation["id"] for citation in result["citations"]} == {target.id}
    assert all("source" not in citation for citation in result["citations"])


def test_refactoring_plan_rejects_fabricated_evidence(demo_graph, demo_intelligence):
    target = symbol(demo_graph, "PaymentService")

    class Fabricator:
        def complete(self, messages):
            return {"content": json.dumps(generated_payload(target.id, "invented-symbol"))}

    result = RefactoringPlanner(demo_intelligence, Fabricator()).plan(target.id, "Change payment processing safely")

    assert result["grounding"] == "static-evidence"
    assert "outside the impact graph" in result["warning"]
    assert all(
        evidence_id in demo_intelligence.nodes for stage in result["stages"] for evidence_id in stage["evidence_ids"]
    )


def test_refactoring_plan_has_deterministic_fallback_and_test_signal(demo_graph, demo_intelligence):
    target = symbol(demo_graph, "verify_token")
    result = RefactoringPlanner(demo_intelligence, Unavailable()).plan(
        target.id, "Rotate token verification without breaking authentication"
    )

    assert result["grounding"] == "static-evidence"
    assert result["warning"]
    assert len(result["stages"]) >= 3
    assert result["missing_test_signal"] is True
    assert result["impact"]["caveat"]
    assert result["graph"]["nodes"]


def test_refactoring_plan_rejects_unknown_symbol(demo_intelligence):
    try:
        RefactoringPlanner(demo_intelligence, Unavailable()).plan("missing", "Change this implementation safely")
    except KeyError as exc:
        assert exc.args == ("missing",)
    else:
        raise AssertionError("Unknown symbols must be rejected")


def test_refactoring_plan_includes_statically_connected_tests(parse):
    from app.graph.intelligence import Intelligence

    graph = parse(
        {
            "app.py": "def process_order(value):\n    return value\n",
            "tests/test_app.py": (
                "from app import process_order\n\n"
                "def test_process_order():\n    assert process_order('order') == 'order'\n"
            ),
        }
    )
    intelligence = Intelligence(graph)
    target = next(node for node in graph.nodes if node.name == "process_order" and node.file_path == "app.py")

    result = RefactoringPlanner(intelligence, Unavailable()).plan(
        target.id, "Extract order processing behind a stable interface"
    )

    assert result["related_tests"] == ["tests/test_app.py"]
    assert result["missing_test_signal"] is False
    assert any("tests/test_app.py" in action for stage in result["stages"] for action in stage["actions"])
