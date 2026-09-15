# Manual QA notes

## ItsDangerous assistant test

Question: `How does Serializer.loads verify a signed token, and which methods and exceptions are involved?`

Result: Partially correct (approximately 6/10). The answer correctly mentioned signature verification and `BadSignature`, but it omitted the main flow through `iter_unsigners`, `Signer.unsign`, and `load_payload`. It also mixed `TimedSerializer.loads` options (`max_age` and `return_timestamp`) into the explanation of regular `Serializer.loads`, omitted fallback signers and `BadPayload`, did not cite `signer.py`, and reported an unjustified 90% confidence.

Expected behavior: The answer should distinguish `Serializer.loads` from `TimedSerializer.loads`, explain the verified call chain, name the relevant exceptions, and cite both `serializer.py` and `signer.py`.

## ItsDangerous overview and architecture test

Result: Repository metrics and graph calculations matched the reference run: 15 files, 1,713 lines, 15 functions, 29 classes, 91 methods, 419 nodes, 872 relationships, no API endpoints, and no detected dependency cycles. Connected-component degrees also matched: `pytest` 30, `__init__.py` 23, `want_bytes` 23, `timed.py` 22, and `serializer.py`, `signer.py`, and `url_safe.py` 17 each.

Finding: The architecture explanation named `pytest`, `__init__.py`, `want_bytes`, and `timed.py`, while its displayed citations pointed mainly to `signer.py`, `url_safe.py`, and `serializer.py`. The computed facts were correct, but the citations did not directly support the named hubs.

Expected behavior: Architecture citations should correspond to the components explicitly named in the explanation. For this result they should include `src/itsdangerous/__init__.py`, `src/itsdangerous/encoding.py:want_bytes`, and `src/itsdangerous/timed.py`. An external package such as `pytest` may need relationship evidence rather than a source citation.

Finding: The UI reported 50 potentially unused symbols. This is a static heuristic based on missing incoming references and must not present those symbols as confirmed dead code; public APIs and dynamically invoked code can be false positives.

Finding: The UI correctly reported 274 unresolved relationships and stated that they are excluded from dependency paths and impact calculations. This exclusion can cause impact results to underestimate the true dependency reach and should remain visible to users.

## ItsDangerous `Signer` impact assistant test

Question: `What could be affected if the Signer class changes?`

Result: Partially correct (approximately 5/10). The answer named real direct dependents such as the test `signer` fixture, `Serializer.make_signer`, `Serializer.iter_unsigners`, and `TestSigner`, and correctly described possible effects on signing, verification, and unsigning. It also invoked the `analyze_impact` tool.

Finding: The answer did not present the main deterministic impact result: Medium risk, score 33/100, 8 affected files, 2 affected modules, blast radius 12, and no API or database effects. It omitted the important `TimestampSigner` inheritance relationship and the effects on timed and URL-safe serializers. The displayed 90% confidence was not justified by the incomplete coverage.

Finding: The `serializer.py` citation at lines 278–285 supports `make_signer`, but does not support the separately named `iter_unsigners`, which begins after that range. The answer therefore made one claim without a directly corresponding citation.

Expected behavior: Impact answers should lead with the calculated risk score and blast radius, summarize affected source areas and tests, identify important inheritance such as `TimestampSigner`, distinguish direct from transitive effects, state that no endpoints or database entities are involved, and attach a citation to each important claim.

## ItsDangerous `Signer` impact panel

Result: Passed. The deterministic impact panel matched the backend reference result: Medium risk, score 33/100, 12 dependents, 8 affected files, no API routes, and maximum depth 3. The displayed score contributions were internally consistent: direct dependents +20, transitive dependents +4, API endpoints +0, cross-module reach +3, database writes +0, and dependency depth +6, totaling 33.

Finding: The deterministic impact panel was more complete and reliable than the assistant's prose answer for the same symbol. The assistant should use and summarize these available impact fields instead of returning only a narrow selection of related symbols.
