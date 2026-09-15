from abc import ABC, abstractmethod
from functools import lru_cache
import httpx
from app.config import settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(
            model_name=settings().embedding_model, cache_dir=str(settings().data_dir / "models"), threads=2
        )

    def embed(self, texts):
        return [vector.tolist() for vector in self.model.embed(texts, batch_size=32)]


class CloudEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts):
        s = settings()
        with httpx.Client(timeout=90) as client:
            response = client.post(
                s.embedding_base_url.rstrip("/") + "/embeddings",
                headers={"Authorization": f"Bearer {s.embedding_api_key}"},
                json={"model": s.embedding_model, "input": texts, "dimensions": s.embedding_dimensions},
            )
            response.raise_for_status()
            return [row["embedding"] for row in sorted(response.json()["data"], key=lambda r: r["index"])]


@lru_cache
def get_embeddings():
    provider = settings().embedding_provider
    if provider == "local":
        return LocalEmbeddingProvider()
    if provider in {"cloud", "openai-compatible"}:
        return CloudEmbeddingProvider()
    raise ValueError("EMBEDDING_PROVIDER must be local or cloud")


def embedding_text(node):
    return "\n".join([node.qualified_name, node.signature, node.docstring, node.file_path, node.source[:3500]])[:6000]


def embed_graph(graph, progress=lambda *a: None, cache=None):
    provider = get_embeddings()
    # Keep file summaries small; symbols carry code-level semantic context.
    selected = [n for n in graph.nodes if n.type in {"File", "Function", "Method", "Class", "Interface", "Endpoint"}]
    file_summaries = {}
    for n in graph.nodes:
        if n.type in {"Function", "Class", "Interface"}:
            file_summaries.setdefault(n.file_path, []).append(n.signature)
    result = []
    cache = cache or {}
    unchanged = [
        n
        for n in selected
        if n.id in cache and cache[n.id][0] == n.hash and len(cache[n.id][1]) == settings().embedding_dimensions
    ]
    result.extend({"id": n.id, "embedding": cache[n.id][1]} for n in unchanged)
    ids = {n.id for n in unchanged}
    selected = [n for n in selected if n.id not in ids]
    for start in range(0, len(selected), 32):
        batch = selected[start : start + 32]
        texts = [
            embedding_text(n)
            if n.type != "File"
            else f"{n.file_path}\n" + "\n".join(file_summaries.get(n.file_path, []))[:3000]
            for n in batch
        ]
        vectors = provider.embed(texts)
        if len(vectors) != len(batch) or any(len(v) != settings().embedding_dimensions for v in vectors):
            raise ValueError("Embedding dimensions do not match EMBEDDING_DIMENSIONS")
        result.extend({"id": n.id, "embedding": v} for n, v in zip(batch, vectors))
        progress(min(start + 32, len(selected)), len(selected))
    return result
