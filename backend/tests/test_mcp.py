import json

import pytest
from mcp import Client

from app.mcp import server


class RepositoryStore:
    def repositories(self, owner_id):
        assert owner_id == "local"
        return [
            {
                "id": "repo-ready",
                "name": "Example",
                "status": "READY",
                "languages": ["Python"],
                "updated_at": "2026-01-01T00:00:00Z",
                "source": "private",
            },
            {"id": "repo-failed", "name": "Failed", "status": "FAILED", "source": "private"},
        ]

    def repository(self, repository_id, owner_id):
        assert owner_id == "local"
        if repository_id == "repo-ready":
            return {"id": repository_id, "status": "READY"}
        return None


class StubTools:
    search = None

    def execute(self, name, arguments):
        return {"tool": name, "arguments": arguments}


@pytest.fixture
def local_mcp(monkeypatch):
    monkeypatch.setattr(server, "get_store", lambda: RepositoryStore())
    monkeypatch.setattr(server, "_tools", lambda repository_id: StubTools())
    return server.mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_lists_repositories_without_private_metadata(local_mcp):
    async with Client(local_mcp) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {
            "list_repositories",
            "repository_overview",
            "search_code",
            "get_symbol",
            "read_source",
            "find_callers",
            "find_callees",
            "find_dependency_path",
            "analyze_change_impact",
        }
        assert all(tool.annotations.read_only_hint for tool in tools.tools)
        assert all(tool.annotations.destructive_hint is False for tool in tools.tools)
        result = await client.call_tool("list_repositories", {})
    assert result.structured_content == {
        "result": [
            {
                "repository_id": "repo-ready",
                "name": "Example",
                "status": "READY",
                "languages": ["Python"],
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]
    }


@pytest.mark.anyio
async def test_mcp_maps_public_tool_names_to_bounded_agent_tools(local_mcp):
    async with Client(local_mcp) as client:
        search = await client.call_tool(
            "search_code",
            {"repository_id": "repo-ready", "query": "checkout", "mode": "symbol"},
        )
        impact = await client.call_tool(
            "analyze_change_impact",
            {"repository_id": "repo-ready", "symbol_id": "symbol-1"},
        )
    assert json.loads(search.content[0].text) == {
        "tool": "search_symbol",
        "arguments": {"name": "checkout"},
    }
    assert json.loads(impact.content[0].text) == {
        "tool": "analyze_impact",
        "arguments": {"symbol_id": "symbol-1"},
    }


def test_mcp_rejects_shared_auth_mode(monkeypatch):
    monkeypatch.setattr(server, "settings", lambda: type("Config", (), {"auth_mode": "github"})())
    with pytest.raises(ValueError, match="AUTH_MODE=local"):
        server._local_store()


def test_mcp_scopes_repository_before_loading_intelligence(monkeypatch):
    store = RepositoryStore()
    marker = object()
    monkeypatch.setattr(server, "get_store", lambda: store)
    monkeypatch.setattr(server, "intelligence", lambda repository_id: marker)
    monkeypatch.setattr(server, "AgentTools", lambda graph, selected_store: (graph, selected_store))
    assert server._tools("repo-ready") == (marker, store)
    with pytest.raises(ValueError, match="not found"):
        server._tools("another-owner-repository")
