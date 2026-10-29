"""Neo4j persistence: metadata and versioned graph intelligence are separate labels."""

import json
from collections import defaultdict
from functools import lru_cache
from hashlib import sha256

from neo4j import GraphDatabase

from app.config import settings
from app.graph.snapshots import FORMAT as SNAPSHOT_FORMAT
from app.graph.snapshots import decode_graph_snapshot, encode_graph_snapshot
from app.models.schema import CodeEdge, CodeGraph, CodeNode
from app.parsers.pipeline import RELATIONS


class GraphStore:
    def __init__(self):
        s = settings()
        self.driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_username, s.neo4j_password), connection_timeout=8)

    def query(self, cypher, **parameters):
        with self.driver.session() as session:
            return [dict(record) for record in session.run(cypher, **parameters)]

    def initialize(self):
        self.query("CREATE CONSTRAINT code_id IF NOT EXISTS FOR (n:CodeNode) REQUIRE n.id IS UNIQUE")
        self.query("CREATE CONSTRAINT repository_id IF NOT EXISTS FOR (r:RepositoryMeta) REQUIRE r.id IS UNIQUE")
        self.query("CREATE CONSTRAINT chat_id IF NOT EXISTS FOR (c:ChatSession) REQUIRE c.id IS UNIQUE")
        self.query("CREATE CONSTRAINT guardian_run_id IF NOT EXISTS FOR (g:GuardianRun) REQUIRE g.id IS UNIQUE")
        self.query("CREATE CONSTRAINT graph_snapshot_id IF NOT EXISTS FOR (s:GraphSnapshot) REQUIRE s.id IS UNIQUE")
        self.query("CREATE INDEX code_repository IF NOT EXISTS FOR (n:CodeNode) ON (n.repository_id)")
        self.query(
            "CREATE INDEX guardian_run_repository IF NOT EXISTS FOR (g:GuardianRun) ON (g.repository_id)"
        )
        self.query(
            "CREATE INDEX graph_snapshot_repository IF NOT EXISTS FOR (s:GraphSnapshot) ON (s.repository_id)"
        )
        self.query(
            "CREATE VECTOR INDEX code_embeddings IF NOT EXISTS FOR (n:CodeNode) ON n.embedding OPTIONS {indexConfig: {`vector.dimensions`: $dimensions, `vector.similarity_function`: 'cosine'}}",
            dimensions=settings().embedding_dimensions,
        )

    def create_repository(self, data):
        self.query("CREATE (r:RepositoryMeta) SET r = $data", data=data)
        return data

    def update_repository(self, id, **fields):
        self.query("MATCH (r:RepositoryMeta {id:$id}) SET r += $fields", id=id, fields=fields)

    def fail_sync_if_active(self, id: str, error: str, failed_at: str):
        rows = self.query(
            "MATCH (r:RepositoryMeta {id:$id}) "
            "WHERE r.sync_status IN ['QUEUED', 'CLONING', 'SCANNING', 'PARSING', "
            "'BUILDING_GRAPH', 'EMBEDDING', 'ANALYZING'] "
            "SET r.sync_status='ERROR', r.sync_error=$error, r.sync_message='Synchronization failed', "
            "r.sync_updated_at=$failed_at "
            "RETURN properties(r) AS repo",
            id=id,
            error=error,
            failed_at=failed_at,
        )
        return rows[0]["repo"] if rows else None

    def repository(self, id, owner_id=None):
        ownership = (
            " AND (r.owner_id=$owner_id OR ($owner_id='local' AND r.owner_id IS NULL))"
            if owner_id is not None
            else ""
        )
        rows = self.query(
            f"MATCH (r:RepositoryMeta {{id:$id}}) WHERE true{ownership} RETURN properties(r) AS repo",
            id=id,
            owner_id=owner_id,
        )
        return rows[0]["repo"] if rows else None

    def repositories(self, owner_id=None):
        ownership = (
            "WHERE r.owner_id=$owner_id OR ($owner_id='local' AND r.owner_id IS NULL)"
            if owner_id is not None
            else ""
        )
        return [
            r["repo"]
            for r in self.query(
                f"MATCH (r:RepositoryMeta) {ownership} RETURN properties(r) AS repo "
                "ORDER BY r.created_at DESC LIMIT 100",
                owner_id=owner_id,
            )
        ]

    def github_repository(self, owner: str, name: str, installation_id: int):
        sources = [
            f"https://github.com/{owner}/{name}",
            f"https://github.com/{owner}/{name}.git",
        ]
        parameters = {
            "sources": [source.lower() for source in sources],
            "installation_id": installation_id,
        }
        bound = self.query(
            "MATCH (r:RepositoryMeta) "
            "WHERE r.kind='github' AND r.status='READY' AND toLower(r.source) IN $sources "
            "AND r.github_installation_id=$installation_id "
            "RETURN properties(r) AS repo LIMIT 2",
            **parameters,
        )
        if len(bound) == 1:
            return {"status": "BOUND", "repository": bound[0]["repo"]}
        if len(bound) > 1:
            return {"status": "AMBIGUOUS", "repository": None}
        unbound = self.query(
            "MATCH (r:RepositoryMeta) "
            "WHERE r.kind='github' AND r.status='READY' AND toLower(r.source) IN $sources "
            "AND r.github_installation_id IS NULL "
            "RETURN properties(r) AS repo ORDER BY r.updated_at DESC LIMIT 2",
            **parameters,
        )
        if not unbound:
            return {"status": "NOT_FOUND", "repository": None}
        if len(unbound) > 1:
            return {"status": "AMBIGUOUS", "repository": None}
        repository_id = unbound[0]["repo"]["id"]
        claimed = self.query(
            "MATCH (r:RepositoryMeta {id:$repository_id}) "
            "WHERE r.github_installation_id IS NULL "
            "SET r.github_installation_id=$installation_id "
            "RETURN properties(r) AS repo",
            repository_id=repository_id,
            installation_id=installation_id,
        )
        if claimed:
            return {"status": "BOUND", "repository": claimed[0]["repo"]}
        rebound = self.query(
            "MATCH (r:RepositoryMeta {id:$repository_id, github_installation_id:$installation_id}) "
            "RETURN properties(r) AS repo",
            repository_id=repository_id,
            installation_id=installation_id,
        )
        return (
            {"status": "BOUND", "repository": rebound[0]["repo"]}
            if rebound
            else {"status": "CONFLICT", "repository": None}
        )

    def create_guardian_run(self, data):
        rows = self.query(
            "CREATE (g:GuardianRun) SET g = $data RETURN properties(g) AS run",
            data=data,
        )
        self.prune_guardian_runs(data["repository_id"])
        return rows[0]["run"]

    def prune_guardian_runs(self, repository_id: str, keep: int = 200):
        self.query(
            "MATCH (g:GuardianRun {repository_id:$repository_id}) "
            "WITH g ORDER BY g.created_at DESC SKIP $keep DETACH DELETE g",
            repository_id=repository_id,
            keep=keep,
        )

    def guardian_run(self, id: str, repository_id: str):
        rows = self.query(
            "MATCH (g:GuardianRun {id:$id, repository_id:$repository_id}) "
            "RETURN properties(g) AS run",
            id=id,
            repository_id=repository_id,
        )
        return rows[0]["run"] if rows else None

    def guardian_runs(self, repository_id: str, limit: int = 50):
        return [
            row["run"]
            for row in self.query(
                "MATCH (g:GuardianRun {repository_id:$repository_id}) "
                "RETURN properties(g) AS run ORDER BY g.created_at DESC LIMIT $limit",
                repository_id=repository_id,
                limit=limit,
            )
        ]

    def update_guardian_run(self, id: str, **fields):
        self.query(
            "MATCH (g:GuardianRun {id:$id}) SET g += $fields",
            id=id,
            fields=fields,
        )

    def fail_guardian_run_if_active(self, id: str, error: str, failed_at: str):
        rows = self.query(
            "MATCH (g:GuardianRun {id:$id}) "
            "WHERE g.status IN ['QUEUED', 'RUNNING'] "
            "SET g.status='ERROR', g.error=$error, g.failed_at=$failed_at, g.updated_at=$failed_at "
            "RETURN properties(g) AS run",
            id=id,
            error=error,
            failed_at=failed_at,
        )
        return rows[0]["run"] if rows else None

    def create_guardian_retry(self, source: dict, data: dict):
        """Atomically creates one retry for a failed run.

        The deterministic retry id makes repeated clicks return the same run.
        A failed retry can itself be retried, preserving the full attempt chain.
        """
        rows = self.query(
            "MATCH (source:GuardianRun {id:$source_id, repository_id:$repository_id, status:'ERROR'}) "
            "MERGE (retry:GuardianRun {id:$retry_id}) "
            "ON CREATE SET retry = $data "
            "RETURN properties(retry) AS run",
            source_id=source["id"],
            repository_id=source["repository_id"],
            retry_id=data["id"],
            data=data,
        )
        self.prune_guardian_runs(source["repository_id"])
        return rows[0]["run"] if rows else None

    def save_graph(self, id, graph):
        # One transaction: readers see either the old graph or the complete new graph.
        def write(tx):
            tx.run("MATCH (n:CodeNode {repository_id:$id}) DETACH DELETE n", id=id).consume()
            rows = [n.model_dump() for n in graph.nodes]
            for i in range(0, len(rows), 500):
                tx.run("UNWIND $rows AS row CREATE (n:CodeNode) SET n = row", rows=rows[i : i + 500]).consume()
            grouped = defaultdict(list)
            for edge in graph.edges:
                if edge.type not in RELATIONS:
                    raise ValueError("Unsupported relationship type")
                grouped[edge.type].append(edge.model_dump())
            for kind, rows in grouped.items():
                for i in range(0, len(rows), 500):
                    tx.run(
                        f"UNWIND $rows AS row MATCH (a:CodeNode {{id:row.source}}), (b:CodeNode {{id:row.target}}) CREATE (a)-[r:{kind}]->(b) SET r = row",
                        rows=rows[i : i + 500],
                    ).consume()

        with self.driver.session() as session:
            session.execute_write(write)

    def graph(self, id, with_embeddings=False):
        projection = "properties(n)" if with_embeddings else "n {.*, embedding: []}"
        nodes = self.query(f"MATCH (n:CodeNode {{repository_id:$id}}) RETURN {projection} AS node", id=id)
        edges = self.query(
            "MATCH (a:CodeNode {repository_id:$id})-[r]->(b:CodeNode {repository_id:$id}) RETURN properties(r) AS edge",
            id=id,
        )
        return CodeGraph(nodes=[CodeNode(**n["node"]) for n in nodes], edges=[CodeEdge(**e["edge"]) for e in edges])

    def save_graph_snapshot(self, repository_id: str, commit_sha: str, graph: CodeGraph, created_at: str, trigger: str):
        snapshot_id = sha256(f"{repository_id}:{commit_sha}".encode()).hexdigest()[:32]
        data = {
            "id": snapshot_id,
            "repository_id": repository_id,
            "commit_sha": commit_sha,
            "fingerprint": graph.fingerprint,
            "nodes": len(graph.nodes),
            "relationships": len(graph.edges),
            "created_at": created_at,
            "trigger": trigger,
            "format": SNAPSHOT_FORMAT,
            "payload": encode_graph_snapshot(graph),
        }
        rows = self.query(
            "MERGE (s:GraphSnapshot {id:$id}) SET s += $data RETURN properties(s) AS snapshot",
            id=snapshot_id,
            data=data,
        )
        self.query(
            "MATCH (s:GraphSnapshot {repository_id:$repository_id}) "
            "WITH s ORDER BY s.created_at DESC SKIP $keep DETACH DELETE s",
            repository_id=repository_id,
            keep=20,
        )
        return rows[0]["snapshot"]

    def graph_snapshots(self, repository_id: str, limit: int = 20):
        return [
            row["snapshot"]
            for row in self.query(
                "MATCH (s:GraphSnapshot {repository_id:$repository_id}) "
                "RETURN s {.*, payload: null} AS snapshot ORDER BY s.created_at DESC LIMIT $limit",
                repository_id=repository_id,
                limit=limit,
            )
        ]

    def graph_snapshot(self, repository_id: str, commit_sha: str):
        rows = self.query(
            "MATCH (s:GraphSnapshot {repository_id:$repository_id, commit_sha:$commit_sha}) "
            "RETURN properties(s) AS snapshot",
            repository_id=repository_id,
            commit_sha=commit_sha,
        )
        if not rows:
            return None
        snapshot = rows[0]["snapshot"]
        snapshot["graph"] = decode_graph_snapshot(snapshot.pop("payload"))
        return snapshot

    def update_embeddings(self, rows):
        for i in range(0, len(rows), 100):
            self.query(
                "UNWIND $rows AS row MATCH (n:CodeNode {id:row.id}) SET n.embedding=row.embedding",
                rows=rows[i : i + 100],
            )

    def vector_search(self, id, vector, top_k=20):
        # Exact repository filtering avoids global ANN starvation in multi-repository stores.
        return self.query(
            "MATCH (n:CodeNode {repository_id:$id}) WHERE size(n.embedding) = $dimensions WITH n, vector.similarity.cosine(n.embedding, $vector) AS score RETURN n.id AS id, score ORDER BY score DESC LIMIT $top_k",
            id=id,
            dimensions=len(vector),
            vector=vector,
            top_k=top_k,
        )

    def delete_repository(self, id):
        self.query(
            "MATCH (n) WHERE (n:CodeNode AND n.repository_id=$id) "
            "OR (n:RepositoryMeta AND n.id=$id) "
            "OR (n:ChatSession AND n.repository_id=$id) "
            "OR (n:GraphSnapshot AND n.repository_id=$id) "
            "OR (n:GuardianRun AND n.repository_id=$id) DETACH DELETE n",
            id=id,
        )

    def session(self, id, repository_id):
        rows = self.query(
            "MATCH (c:ChatSession {id:$id, repository_id:$repository_id}) RETURN c.state AS state",
            id=id,
            repository_id=repository_id,
        )
        return json.loads(rows[0]["state"]) if rows else {"messages": [], "symbols": []}

    def save_session(self, id, repository_id, state):
        self.query(
            "MERGE (c:ChatSession {id:$id, repository_id:$repository_id}) SET c.state=$state",
            id=id,
            repository_id=repository_id,
            state=json.dumps(state),
        )


@lru_cache
def get_store():
    return GraphStore()
