# Architecture rules

Regora can evaluate version-controlled architecture quality gates while indexing a repository. Add `.regora.yml` or `.regora.yaml` at the repository root:

```yaml
version: 1
rules:
  - id: controller-database-boundary
    name: Controllers cannot call the database directly
    type: forbid_dependency
    from: src/controllers/**
    to: src/database/**
    relationships: [CALLS, IMPORTS, REFERENCES]
    severity: error

  - id: dependency-cycles
    name: Avoid dependency cycles
    type: no_cycles
    severity: warning
```

Reindex the repository after changing its policy. Results appear under **Overview → Architecture quality gates** and at:

```text
GET /api/repositories/{repository_id}/architecture-policy
```

To enforce the policy in CI after the repository has been indexed:

```bash
curl --fail http://localhost:3000/api/repositories/$REGORA_REPOSITORY_ID/architecture-policy/check
```

The check returns HTTP `409` for `FAIL` or `INVALID`, and HTTP `200` for `PASS`, `WARN`, or `NOT_CONFIGURED`. Authentication still applies when Regora uses GitHub mode.

## Rule types

### `forbid_dependency`

Fails when a resolved static dependency directly connects a source path matching `from` to a target path matching `to`. Patterns use shell-style globs. The optional `relationships` list limits which graph relationships are checked. When omitted, all dependency relationships are checked.

Supported relationships are `CALLS`, `IMPORTS`, `REFERENCES`, `EXTENDS`, `IMPLEMENTS`, `HANDLES`, `ROUTES_TO`, `DEPENDS_ON`, `USES_PACKAGE`, `READS_FROM`, and `WRITES_TO`.

### `no_cycles`

Reports each dependency cycle found by Regora's bounded strongly-connected-component analysis.

## Results and limits

Each violation includes the involved symbols, graph path, relationship type, source file, source line, confidence, and resolution. Clicking a violation in the workspace highlights its graph evidence.

- `severity: error` produces a failed policy.
- `severity: warning` produces a warning when there are no errors.
- A repository without a policy remains valid and reports `NOT_CONFIGURED`.
- Invalid policy YAML is reported as `INVALID`; repository indexing still completes.
- Policies are limited to 64 KB and 50 rules. Each rule returns at most 50 violations, with 100 violations in the combined result.

These checks use static evidence. Dynamic imports, reflection, runtime dependency injection, and unresolved relationships may not be visible.
