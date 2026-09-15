import re
from app.embeddings.providers import get_embeddings


class HybridRetrieval:
    def __init__(self, intelligence, store=None):
        self.intelligence = intelligence
        self.store = store

    def search(self, query, mode="hybrid", top_k=10):
        top_k = min(50, max(1, top_k))
        q = query.lower().strip()
        tokens = set(re.findall(r"[a-z][a-z0-9_]+", q)) - {
            "what",
            "where",
            "does",
            "the",
            "this",
            "that",
            "how",
            "which",
            "are",
            "is",
            "if",
            "it",
            "to",
            "from",
            "a",
            "an",
            "of",
            "in",
            "handled",
        }
        semantic = {}
        warning = None
        if mode in {"semantic", "hybrid"} and self.store:
            try:
                rid = next(iter(self.intelligence.nodes.values())).repository_id
                vector = get_embeddings().embed([query])[0]
                semantic = {
                    row["id"]: row["score"] for row in self.store.vector_search(rid, vector, max(top_k * 3, 30))
                }
            except Exception as exc:
                warning = (
                    f"Semantic retrieval unavailable ({type(exc).__name__}); symbol and text search remain available."
                )
                if mode == "semantic":
                    return {"results": [], "warning": warning, "mode": mode}
        results = []
        for node in self.intelligence.graph.nodes:
            if node.type in {"Repository", "Directory", "UnresolvedSymbol", "Module"}:
                continue
            name = node.name.lower()
            text = (node.qualified_name + " " + node.docstring + " " + node.source).lower()
            exact = 1.0 if q == name else 0.9 if name in tokens else 0.65 if q in name else 0.0
            lexical = sum(token in text for token in tokens) / max(1, len(tokens))
            similarity = semantic.get(node.id, 0)
            if mode == "symbol":
                score = exact
            elif mode == "text":
                score = 1.0 if q in text else 0
            elif mode == "semantic":
                score = similarity
            else:
                score = 0.50 * similarity + 0.25 * lexical + exact
                if node.type == "File":
                    score *= 0.65
            if score > 0:
                public = node.model_dump(exclude={"embedding", "source"})
                public.update(
                    score=round(score, 4),
                    semantic_score=round(similarity, 4),
                    mechanism="symbol" if exact else "semantic" if similarity > 0 else "text",
                    snippet=node.source[:450],
                )
                results.append(public)
        results.sort(key=lambda n: n["score"], reverse=True)
        return {"results": results[:top_k], "warning": warning, "mode": mode}
