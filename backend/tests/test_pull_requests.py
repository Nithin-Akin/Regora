import pytest

from app.services.pull_requests import (
    analyze_pull_request,
    changed_line_ranges,
    parse_pull_request_url,
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
