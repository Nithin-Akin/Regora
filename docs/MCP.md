# Regora MCP server

Regora exposes its indexed repository graph to MCP-compatible coding agents through Streamable HTTP.

## Start Regora

```bash
cp .env.example .env
docker compose up -d --build
```

Open <http://localhost:3000>, index a repository, and wait until its status is **Indexed**. The MCP endpoint is then available at:

```text
http://localhost:8000/mcp/
```

The initial MCP release supports the default `AUTH_MODE=local`. It intentionally refuses connections to shared GitHub-authenticated workspaces until per-user MCP access tokens are available. The endpoint binds to localhost in the supplied Compose configuration.

## Connect a client

### Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.regora]
url = "http://localhost:8000/mcp/"
```

Restart Codex after saving the configuration.

### Cursor

Add this to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "regora": {
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```

### Claude Code

```bash
claude mcp add --transport http regora http://localhost:8000/mcp/
```

## Available tools

| Tool | Purpose |
|---|---|
| `list_repositories` | Find available repository IDs and indexing status |
| `repository_overview` | Read architecture metrics, hubs, cycles, and health signals |
| `get_architecture_policy` | Read architecture-rule status and exact violation evidence |
| `search_code` | Run hybrid, semantic, literal-text, or symbol search |
| `get_symbol` | Inspect a symbol and its immediate graph neighborhood |
| `read_source` | Read the indexed source excerpt for a symbol |
| `find_callers` | Find incoming resolved calls |
| `find_callees` | Find outgoing resolved calls |
| `find_dependency_path` | Find a directed dependency path between symbols |
| `analyze_change_impact` | Calculate static blast radius and explainable risk |

Every tool after `list_repositories` requires a `repository_id`. Symbol tools use stable IDs returned by search or other tool results. Results are bounded, read-only static-analysis evidence. MCP cannot execute repository code, run shell commands, mutate the graph, or issue arbitrary Cypher.

Try asking your coding agent:

```text
Use Regora to list my indexed repositories. In the Northstar Commerce repository,
find the checkout handler and explain its downstream dependencies with source evidence.
```

```text
Use Regora to find Serializer.loads, then analyze what could be affected if it changes.
Include the affected files and tests.
```
