from hashlib import sha256
from typing import Any, Literal
from pydantic import BaseModel, Field


def stable_id(*parts: str) -> str:
    return sha256(":".join(parts).encode()).hexdigest()[:24]


class CodeNode(BaseModel):
    id: str
    name: str
    type: str
    repository_id: str
    qualified_name: str = ""
    file_path: str = ""
    language: str = ""
    start_line: int = 1
    end_line: int = 1
    signature: str = ""
    source: str = ""
    docstring: str = ""
    hash: str = ""
    module: str = ""
    exported: bool = False
    parameters: str = ""
    returns: str = ""
    embedding: list[float] = Field(default_factory=list)


class CodeEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    source_file: str = ""
    source_line: int = 1
    confidence: float = 1.0
    resolution: Literal["resolved", "probable", "unresolved"] = "resolved"
    analysis_method: str = "tree-sitter"


class CodeGraph(BaseModel):
    nodes: list[CodeNode] = Field(default_factory=list)
    edges: list[CodeEdge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fingerprint: str = ""


class GitHubRequest(BaseModel):
    url: str = Field(max_length=250)


class PullRequestRequest(BaseModel):
    url: str = Field(max_length=300)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=100)
    symbol_id: str | None = None


class TraceRequest(BaseModel):
    source_id: str
    target_id: str | None = None


class Citation(BaseModel):
    symbol_id: str
    file: str
    start_line: int
    end_line: int


class Answer(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)
    symbols: list[str] = Field(default_factory=list)
    paths: list[list[str]] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    grounding: str = "static-evidence"
    intent: str = "explanation"
    session_id: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    warning: str | None = None
