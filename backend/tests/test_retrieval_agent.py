import json
import pytest
from app.retrieval.hybrid import HybridRetrieval
from app.agents.reasoning import RepoAgent, intent
from app.agents.tools import AgentTools
from app.models.schema import AskRequest
from conftest import symbol


class SessionStore:
    def __init__(self):
        self.state = {}

    def session(self, id, rid):
        return self.state.get(id, {"messages": [], "symbols": []})

    def save_session(self, id, rid, state):
        self.state[id] = state

    def vector_search(self, *args):
        raise ConnectionError("offline")


class Unavailable:
    def complete(self, *args):
        raise ConnectionError("offline")


@pytest.fixture(autouse=True)
def no_model_download(monkeypatch):
    class Embedding:
        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("app.retrieval.hybrid.get_embeddings", lambda: Embedding())


def test_exact_symbol_priority(demo_intelligence):
    result = HybridRetrieval(demo_intelligence).search("What depends on PaymentService?")
    assert result["results"][0]["name"] == "PaymentService"


def test_text_and_symbol_search(demo_intelligence):
    assert HybridRetrieval(demo_intelligence).search("JWT_SECRET", "text")["results"]
    assert HybridRetrieval(demo_intelligence).search("verify_token", "symbol")["results"][0]["name"] == "verify_token"


def test_semantic_provider_failure_not_faked(demo_intelligence):
    result = HybridRetrieval(demo_intelligence, SessionStore()).search("authentication", "semantic")
    assert result["results"] == [] and result["warning"]


def test_tool_scope_and_unknown_tools(demo_intelligence):
    tools = AgentTools(demo_intelligence, SessionStore())
    with pytest.raises(ValueError):
        tools.execute("run_cypher", {})
    with pytest.raises(ValueError):
        tools.execute("get_source", {"symbol_id": "outside-repository"})


def test_fallback_is_grounded_and_followups(demo_graph, demo_intelligence):
    store = SessionStore()
    agent = RepoAgent(demo_intelligence, store, Unavailable())
    answer = agent.ask(AskRequest(question="What could break if I modify verify_token?"))
    assert answer.grounding == "static-evidence"
    assert "computed" in answer.answer
    assert answer.citations
    for c in answer.citations:
        assert c.symbol_id in demo_intelligence.nodes
        assert c.start_line <= c.end_line
    next_answer = agent.ask(AskRequest(question="What calls it?", session_id=answer.session_id))
    assert symbol(demo_graph, "verify_token").id in next_answer.symbols


def test_rejects_fabricated_citations(demo_intelligence):
    class Fabricator:
        def complete(self, *args):
            return {"content": json.dumps({"answer": "Invented answer", "confidence": 1, "symbols": ["invented"]})}

    answer = RepoAgent(demo_intelligence, SessionStore(), Fabricator()).ask(AskRequest(question="Explain verify_token"))
    assert answer.grounding == "static-evidence"
    assert "Invented answer" not in answer.answer


def test_llm_selects_tools_and_validates_answer(demo_graph, demo_intelligence):
    token = symbol(demo_graph, "verify_token")

    class ToolLLM:
        step = 0

        def complete(self, messages, tools):
            self.step += 1
            if self.step == 1:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "get_source", "arguments": json.dumps({"symbol_id": token.id})},
                        }
                    ],
                }
            assert messages[-1]["role"] == "tool"
            return {
                "content": json.dumps(
                    {
                        "answer": "verify_token validates a signed JWT.",
                        "confidence": 0.8,
                        "symbols": [token.id],
                        "edge_ids": [],
                    }
                )
            }

    answer = RepoAgent(demo_intelligence, SessionStore(), ToolLLM()).ask(AskRequest(question="Explain verify_token"))
    assert answer.grounding == "llm-with-evidence"
    assert any(t["name"] == "get_source" for t in answer.tool_calls)


def test_intents():
    assert intent("What could break if token changes?") == "impact"
    assert intent("Trace checkout to database") == "path"
    assert intent("How is it structured?") == "architecture"


def test_serialized_context_budget_includes_metadata():
    from app.agents.reasoning import bounded_evidence

    budget = [4000]
    value = {
        "nodes": [
            {
                "id": str(i),
                "name": "function",
                "type": "Function",
                "file_path": "a.py",
                "source": "x" * 3000,
                "start_line": 1,
                "end_line": 100,
            }
            for i in range(100)
        ]
    }
    result = bounded_evidence(value, budget)
    assert len(json.dumps(result)) <= 4000
    assert budget[0] >= 0


def test_class_endpoint_dependency_question(demo_intelligence):
    answer = RepoAgent(demo_intelligence, SessionStore(), Unavailable()).ask(
        AskRequest(question="Which API endpoints depend on UserService?")
    )
    assert answer.intent == "dependency"
    assert "POST /checkout" in answer.answer
    assert answer.paths


def test_outgoing_dependency_direction(demo_intelligence):
    answer = RepoAgent(demo_intelligence, SessionStore(), Unavailable()).ask(
        AskRequest(question="What does PaymentService depend on?")
    )
    assert any(call["name"] == "get_dependencies" for call in answer.tool_calls)
