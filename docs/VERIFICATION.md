# Verification report

Verified on 2026-09-14 against the local Docker stack.

- Backend: 60 tests passed (parser, graph, security, retrieval, agent, API, pull request impact, and assistant streaming).
- Frontend: 4 deterministic tests passed.
- Browser: 2 tests passed against the running application, covering import controls, graph rendering, symbol search, source line highlights, impact, and mobile width.
- Next.js production build and Docker Compose configuration passed.
- Fresh ZIP upload: 2 files, 6 nodes, 8 relationships; semantic search returned real embedded results.
- Fresh public GitHub import (`pallets/itsdangerous`): 15 files, 419 nodes, 872 relationships; semantic search passed.
- Reindex: completed through HTTP and RQ; unchanged source retained its fingerprint.
- Neo4j vector index is online, and persisted vectors have 384 dimensions.

## Demo evaluation

```json
{
  "retrieval_hit_rate_at_5": 0.8,
  "known_dependency_recall": 1.0,
  "path_accuracy": 1.0,
  "citation_correctness": 1.0,
  "answer_evidence_coverage": 1.0,
  "llm_answer_count": 1
}
```

See [evaluation-results.json](evaluation-results.json) for the actual retrieval candidates, ground-truth edges, paths, and answers. This is a small curated evaluation, not a general benchmark. Citation checks verify source identities and line bounds; evidence coverage is not a proof of every natural-language claim.

The CPU-only local Ollama model generated one validated answer; the other used the explicitly labeled deterministic fallback. Local generation can take minutes on this machine. Native Ollama or a stronger compatible cloud model is supported for faster or better explanations. Graph exploration, semantic search, source inspection, and impact analysis remain independent of language-model availability.
