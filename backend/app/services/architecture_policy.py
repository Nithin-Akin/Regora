"""Version-controlled architecture rules evaluated against static graph evidence."""

from fnmatch import fnmatchcase
from pathlib import Path
import re

import yaml

from app.graph.intelligence import DEPENDENCY_TYPES, Intelligence


POLICY_FILES = (".regora.yml", ".regora.yaml")
RULE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SEVERITIES = {"warning", "error"}
RULE_TYPES = {"forbid_dependency", "no_cycles"}


def empty_policy() -> dict:
    return {
        "configured": False,
        "source": None,
        "status": "NOT_CONFIGURED",
        "summary": {"rules": 0, "passed": 0, "warnings": 0, "errors": 0, "violations": 0},
        "rules": [],
        "violations": [],
        "error": None,
    }


def invalid_policy(source: str, message: str) -> dict:
    result = empty_policy()
    result.update(configured=True, source=source, status="INVALID", error=message)
    return result


def load_architecture_policy(root: Path, intelligence: Intelligence) -> dict:
    path = next((root / name for name in POLICY_FILES if (root / name).is_file()), None)
    if not path:
        return empty_policy()
    try:
        if path.stat().st_size > 64 * 1024:
            raise ValueError("Architecture policy must be 64 KB or smaller")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        rules = validate_policy(document)
        return evaluate_policy(rules, intelligence, path.name)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        return invalid_policy(path.name, str(exc)[:500])


def validate_policy(document) -> list[dict]:
    if not isinstance(document, dict):
        raise ValueError("Architecture policy must be a YAML object")
    if document.get("version") != 1:
        raise ValueError("Architecture policy version must be 1")
    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("Architecture policy must contain at least one rule")
    if len(raw_rules) > 50:
        raise ValueError("Architecture policy supports at most 50 rules")
    validated = []
    seen = set()
    for position, raw in enumerate(raw_rules, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Rule {position} must be a YAML object")
        rule_id = raw.get("id")
        kind = raw.get("type")
        severity = raw.get("severity", "error")
        name = raw.get("name", rule_id)
        if not isinstance(rule_id, str) or not RULE_ID.fullmatch(rule_id) or rule_id in seen:
            raise ValueError(f"Rule {position} has an invalid or duplicate id")
        if kind not in RULE_TYPES:
            raise ValueError(f"Rule {rule_id} has an unsupported type")
        if severity not in SEVERITIES:
            raise ValueError(f"Rule {rule_id} severity must be warning or error")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError(f"Rule {rule_id} has an invalid name")
        rule = {"id": rule_id, "name": name.strip(), "type": kind, "severity": severity}
        if kind == "forbid_dependency":
            for key in ("from", "to"):
                value = raw.get(key)
                if not isinstance(value, str) or not value.strip() or len(value) > 200:
                    raise ValueError(f"Rule {rule_id} requires a valid {key} glob")
                rule[key] = value.strip()
            relationships = raw.get("relationships", sorted(DEPENDENCY_TYPES))
            if (
                not isinstance(relationships, list)
                or not relationships
                or len(relationships) > 20
                or any(item not in DEPENDENCY_TYPES for item in relationships)
            ):
                raise ValueError(f"Rule {rule_id} contains unsupported relationships")
            rule["relationships"] = relationships
        seen.add(rule_id)
        validated.append(rule)
    return validated


def _location(node) -> str:
    return node.file_path or node.module or node.qualified_name or node.name


def _node(node) -> dict:
    return {
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "file_path": node.file_path,
        "start_line": node.start_line,
        "end_line": node.end_line,
    }


def evaluate_policy(rules: list[dict], intelligence: Intelligence, source: str = ".regora.yml") -> dict:
    results = []
    violations = []
    edges = [
        edge
        for edge in intelligence.graph.edges
        if edge.type in DEPENDENCY_TYPES and edge.resolution != "unresolved"
    ]
    for rule in rules:
        found = []
        if rule["type"] == "forbid_dependency":
            for edge in edges:
                source_node = intelligence.nodes[edge.source]
                target_node = intelligence.nodes[edge.target]
                if (
                    edge.type in rule["relationships"]
                    and fnmatchcase(_location(source_node), rule["from"])
                    and fnmatchcase(_location(target_node), rule["to"])
                ):
                    found.append(
                        {
                            "rule_id": rule["id"],
                            "severity": rule["severity"],
                            "message": (
                                f"{_location(source_node)} {edge.type.lower().replace('_', ' ')} "
                                f"{_location(target_node)}"
                            ),
                            "path": [edge.source, edge.target],
                            "nodes": [_node(source_node), _node(target_node)],
                            "evidence": [edge.model_dump()],
                        }
                    )
                    if len(found) == 50:
                        break
        else:
            for cycle in intelligence.overview()["cycles"]:
                evidence = []
                for left, right in zip(cycle, cycle[1:]):
                    edge = next((item for item in edges if item.source == left and item.target == right), None)
                    if edge:
                        evidence.append(edge.model_dump())
                found.append(
                    {
                        "rule_id": rule["id"],
                        "severity": rule["severity"],
                        "message": "Dependency cycle: "
                        + " → ".join(intelligence.nodes[node_id].name for node_id in cycle),
                        "path": cycle,
                        "nodes": [_node(intelligence.nodes[node_id]) for node_id in dict.fromkeys(cycle)],
                        "evidence": evidence,
                    }
                )
        status = "PASS" if not found else "FAIL" if rule["severity"] == "error" else "WARN"
        results.append({**rule, "status": status, "violation_count": len(found), "violations": found})
        violations.extend(found)
    errors = sum(result["violation_count"] for result in results if result["severity"] == "error")
    warnings = sum(result["violation_count"] for result in results if result["severity"] == "warning")
    return {
        "configured": True,
        "source": source,
        "status": "FAIL" if errors else "WARN" if warnings else "PASS",
        "summary": {
            "rules": len(results),
            "passed": sum(result["status"] == "PASS" for result in results),
            "warnings": warnings,
            "errors": errors,
            "violations": errors + warnings,
        },
        "rules": results,
        "violations": violations[:100],
        "error": None,
    }
