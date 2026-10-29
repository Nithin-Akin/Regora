"""Compact, embedding-free serialization for versioned code graphs."""

import base64
import json
import zlib

from app.models.schema import CodeGraph

FORMAT = "zlib-json-v1"


def encode_graph_snapshot(graph: CodeGraph) -> str:
    data = graph.model_dump()
    for node in data["nodes"]:
        node["embedding"] = []
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    return base64.b64encode(zlib.compress(raw, level=6)).decode()


def decode_graph_snapshot(payload: str) -> CodeGraph:
    try:
        raw = zlib.decompress(base64.b64decode(payload, validate=True))
        return CodeGraph.model_validate_json(raw)
    except (ValueError, TypeError, zlib.error) as exc:
        raise ValueError("Stored graph snapshot is invalid") from exc
