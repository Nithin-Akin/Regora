import pytest

import app.services.pull_requests as pull_requests

from app.graph.intelligence import Intelligence
from app.services.pull_requests import (
    analyze_pull_request,
    changed_line_ranges,
    parse_pull_request_url,
    publish_pull_request_comment,
    validate_pull_request_repository,
)


def payload():
    return {
        "owner": "acme",
        "repository": "shop",
        "pull_request": {
            "number": 12,
            "title": "Change authentication",
            "html_url": "https://github.com/acme/shop/pull/12",
            "state": "open",
            "base": {"ref": "main"},
            "head": {"ref": "auth-change"},
        },
        "files": [
            {
                "filename": "services/auth.py",
                "status": "modified",
                "additions": 2,
                "deletions": 1,
                "patch": "@@ -4,6 +4,7 @@\n class AuthService:\n",
            }
        ],
        "truncated": False,
    }


def test_pull_request_url_and_hunks_are_bounded():
    assert parse_pull_request_url("https://github.com/acme/shop/pull/12") == ("acme", "shop", 12)
    assert changed_line_ranges("@@ -4,6 +8,3 @@") == [(4, 9), (8, 10)]
    with pytest.raises(ValueError):
        parse_pull_request_url("https://evil.test/acme/shop/pull/12")


def test_pull_request_maps_changed_lines_to_graph_impact(demo_intelligence):
    result = analyze_pull_request(
        demo_intelligence,
        {"kind": "github", "source": "https://github.com/acme/shop"},
        payload(),
    )
    assert result["summary"]["files_changed"] == 1
    assert result["summary"]["symbols_changed"] >= 1
    assert any(item["node"]["name"] == "AuthService" for item in result["impacts"])
    assert result["graph"]["nodes"]
    assert result["review"]["grounding"] == "static-evidence"
    assert result["review"]["coverage_gaps"]
    assert result["review"]["status"] == "ATTENTION"


def test_pull_request_review_finds_connected_tests(parse):
    graph = parse(
        {
            "service.py": "def charge():\n    return True\n",
            "tests/test_service.py": "from service import charge\n\ndef test_charge():\n    assert charge()\n",
        }
    )
    result = analyze_pull_request(
        Intelligence(graph),
        {"kind": "github", "source": "https://github.com/acme/shop"},
        {
            **payload(),
            "files": [
                {
                    "filename": "service.py",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "patch": "@@ -1,2 +1,2 @@",
                }
            ],
        },
    )
    charge = next(item for item in result["impacts"] if item["node"]["name"] == "charge")
    assert charge["related_tests"] == ["tests/test_service.py"]
    assert result["review"]["related_tests"] == ["tests/test_service.py"]
    assert not result["review"]["coverage_gaps"]
    assert result["review"]["checklist"][1]["status"] == "pass"


def test_pull_request_must_match_indexed_repository(demo_intelligence):
    with pytest.raises(ValueError, match="indexed GitHub repository"):
        analyze_pull_request(
            demo_intelligence,
            {"kind": "github", "source": "https://github.com/other/project"},
            payload(),
        )
    with pytest.raises(ValueError, match="indexed GitHub repository"):
        validate_pull_request_repository(
            {"kind": "github", "source": "https://github.com/other/project"},
            "https://github.com/acme/shop/pull/12",
        )


def test_publish_pull_request_comment_uses_bounded_github_contract(monkeypatch):
    captured = {}

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {
                "id": 91,
                "html_url": "https://github.com/acme/shop/pull/12#issuecomment-91",
                "created_at": "2026-10-04T10:00:00Z",
            }

    class Client:
        def __init__(self, **kwargs):
            captured["headers"] = kwargs["headers"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        @staticmethod
        def post(url, json):
            captured["url"] = url
            captured["json"] = json
            return Response()

    monkeypatch.setattr(pull_requests.httpx, "Client", Client)
    result = publish_pull_request_comment(
        "https://github.com/acme/shop/pull/12",
        "## Regora review\nGrounded evidence.",
        "secret-token",
    )
    assert captured["url"] == "https://api.github.com/repos/acme/shop/issues/12/comments"
    assert captured["json"] == {"body": "## Regora review\nGrounded evidence."}
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert result["id"] == 91
    assert result["action"] == "created"


def test_publish_pull_request_comment_requires_github_credentials():
    with pytest.raises(pull_requests.GitHubPublishError) as exc:
        publish_pull_request_comment("https://github.com/acme/shop/pull/12", "Review", "")
    assert exc.value.status_code == 401
