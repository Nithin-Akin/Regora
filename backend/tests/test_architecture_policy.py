from pathlib import Path

from app.graph.intelligence import Intelligence
from app.services.architecture_policy import evaluate_policy, load_architecture_policy, validate_policy


def test_forbidden_dependency_has_exact_edge_evidence(parse):
    graph = parse(
        {
            "api/routes.py": "from data.store import save\ndef checkout():\n    save()\n",
            "data/store.py": "def save():\n    return True\n",
        }
    )
    policy = validate_policy(
        {
            "version": 1,
            "rules": [
                {
                    "id": "api-data-boundary",
                    "name": "API cannot call data directly",
                    "type": "forbid_dependency",
                    "from": "api/**",
                    "to": "data/**",
                    "relationships": ["CALLS"],
                    "severity": "error",
                }
            ],
        }
    )
    result = evaluate_policy(policy, Intelligence(graph))
    assert result["status"] == "FAIL"
    assert result["summary"]["errors"] == 1
    violation = result["violations"][0]
    assert len(violation["path"]) == 2
    assert violation["evidence"][0]["type"] == "CALLS"
    assert violation["evidence"][0]["source_file"] == "api/routes.py"


def test_cycle_rule_can_be_a_warning(demo_intelligence):
    result = evaluate_policy(
        [{"id": "cycles", "name": "Avoid cycles", "type": "no_cycles", "severity": "warning"}],
        demo_intelligence,
    )
    assert result["status"] == "WARN"
    assert result["summary"]["warnings"] >= 1
    assert result["violations"][0]["evidence"]


def test_missing_and_invalid_policy_are_reported_without_failing_indexing(tmp_path, demo_intelligence):
    assert load_architecture_policy(tmp_path, demo_intelligence)["status"] == "NOT_CONFIGURED"
    Path(tmp_path, ".regora.yml").write_text("version: 2\nrules: []\n")
    invalid = load_architecture_policy(tmp_path, demo_intelligence)
    assert invalid["status"] == "INVALID"
    assert "version" in invalid["error"]
