"""Neo4j persistence: metadata and versioned graph intelligence are separate labels."""

import json
from collections import defaultdict
from functools import lru_cache
from neo4j import GraphDatabase
from app.config import settings
from app.models.schema import CodeGraph, CodeNode, CodeEdge
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
        self.query("CREATE INDEX code_repository IF NOT EXISTS FOR (n:CodeNode) ON (n.repository_id)")
        self.query(
            "CREATE VECTOR INDEX code_embeddings IF NOT EXISTS FOR (n:CodeNode) ON n.embedding OPTIONS {indexConfig: {`vector.dimensions`: $dimensions, `vector.similarity_function`: 'cosine'}}",
            dimensions=settings().embedding_dimensions,
        )

    def create_repository(self, data):
        self.query("CREATE (r:RepositoryMeta) SET r = $data", data=data)
        return data

    def update_repository(self, id, **fields):
        self.query("MATCH (r:RepositoryMeta {id:$id}) SET r += $fields", id=id, fields=fields)

    def repository(self, id):
        rows = self.query("MATCH (r:RepositoryMeta {id:$id}) RETURN properties(r) AS repo", id=id)
        return rows[0]["repo"] if rows else None

    def repositories(self):
        return [
            r["repo"]
            for r in self.query(
                "MATCH (r:RepositoryMeta) RETURN properties(r) AS repo ORDER BY r.created_at DESC LIMIT 100"
            )
        ]

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
            "MATCH (n) WHERE (n:CodeNode AND n.repository_id=$id) OR (n:RepositoryMeta AND n.id=$id) OR (n:ChatSession AND n.repository_id=$id) DETACH DELETE n",
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
