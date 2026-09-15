from pathlib import Path, PurePosixPath
import posixpath
import re
from app.config import settings
from app.models.schema import CodeGraph, CodeNode, CodeEdge, stable_id
from app.parsers.analyzers import ADAPTERS
from app.security.repositories import scan_files

RELATIONS = {
    "CONTAINS",
    "DEFINES",
    "IMPORTS",
    "CALLS",
    "REFERENCES",
    "EXTENDS",
    "IMPLEMENTS",
    "HANDLES",
    "ROUTES_TO",
    "READS_FROM",
    "WRITES_TO",
    "DEPENDS_ON",
    "USES_PACKAGE",
    "BELONGS_TO",
}


def analyze_repository(root: Path, repository_id: str, progress=lambda *args: None) -> CodeGraph:
    files = scan_files(root)
    parsed = []
    adapters = {}
    for i, path in enumerate(files):
        adapter = adapters.setdefault(path.suffix, ADAPTERS[path.suffix]())
        parsed.append(
            adapter.analyze(repository_id, path.relative_to(root).as_posix(), path.read_text(errors="replace"))
        )
        if i % 25 == 0:
            progress(i, len(files))
    return resolve_graph(repository_id, parsed)


def resolve_graph(repository_id, parsed):
    nodes = {}
    edges = {}
    warnings = [warning for file in parsed for warning in file.warnings]

    def add(node):
        nodes[node.id] = node
        if len(nodes) > settings().max_nodes:
            raise ValueError("Repository exceeds maximum graph size")
        return node.id

    def edge(a, b, kind, file, line=1, resolution="resolved", method="tree-sitter"):
        if a == b and kind in {"CONTAINS", "DEFINES"}:
            return
        id = stable_id(a, b, kind, file, str(line))
        edges[id] = CodeEdge(
            id=id,
            source=a,
            target=b,
            type=kind,
            source_file=file,
            source_line=line,
            resolution=resolution,
            confidence=1.0 if resolution == "resolved" else 0.65 if resolution == "probable" else 0.0,
            analysis_method=method,
        )

    repo = add(CodeNode(id=repository_id, name="Repository", type="Repository", repository_id=repository_id))
    by_file = {p.node.file_path: p for p in parsed}
    symbols = {}
    for p in parsed:
        path = p.node.file_path
        parent = repo
        for directory in reversed(PurePosixPath(path).parents):
            if str(directory) == ".":
                continue
            id = stable_id(repository_id, "dir", str(directory))
            add(
                CodeNode(
                    id=id,
                    name=directory.name,
                    type="Directory",
                    repository_id=repository_id,
                    file_path=str(directory),
                    module=str(directory),
                )
            )
            edge(parent, id, "CONTAINS", path)
            parent = id
        add(p.node)
        edge(parent, p.node.id, "CONTAINS", path)
        for symbol in p.symbols:
            add(symbol)
            symbols[(path, symbol.qualified_name.split(":", 1)[1])] = symbol.id
        for route, _ in p.endpoints:
            add(route)
            edge(p.node.id, route.id, "DEFINES", path, route.start_line)

    def module_path(path, module):
        py = path.endswith(".py")
        if py:
            if module.startswith("."):
                level = len(module) - len(module.lstrip("."))
                base = str(PurePosixPath(path).parent)
                for _ in range(level - 1):
                    base = posixpath.dirname(base)
                value = posixpath.join(base, module.lstrip(".").replace(".", "/"))
            else:
                value = module.replace(".", "/")
            candidates = [value + ".py", value + "/__init__.py"]
            # Conventional src layout.
            candidates += ["src/" + candidate for candidate in candidates]
        else:
            if not module.startswith("."):
                return None
            value = posixpath.normpath(posixpath.join(str(PurePosixPath(path).parent), module))
            base = value.rsplit(".", 1)[0] if value.endswith((".js", ".jsx", ".mjs")) else value
            candidates = [value] + [
                base + suffix for suffix in (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js")
            ]
        return next((candidate for candidate in candidates if candidate in by_file), None)

    def resolve(p, target, scope="", seen=None):
        seen = set() if seen is None else seen
        key = (p.node.file_path, target, scope)
        if key in seen or len(seen) > 20:
            return None
        seen.add(key)
        path = p.node.file_path
        if target in nodes:
            return target
        target = target.removesuffix("()")
        # Parameters and assigned locals shadow imports and outer definitions.
        scopes = scope.split(".") if scope else []
        root_name = target.split(".")[0]
        for length in range(len(scopes), -1, -1):
            key = f"{'.'.join(scopes[:length])}:{root_name}"
            if key in p.shadowed and len(target.split(".")) == 1 and key not in p.bindings:
                return None
        # Lexical functions/classes first; never match arbitrary names across files.
        scopes = scope.split(".") if scope else []
        for i in range(len(scopes), -1, -1):
            q = ".".join(scopes[:i] + [target])
            if (path, q) in symbols:
                return symbols[(path, q)]
        parts = target.split(".")
        if parts[0] in {"self", "cls", "this"} and len(parts) > 1:
            owner_class = next(
                (
                    ".".join(scopes[:i])
                    for i in range(len(scopes), 0, -1)
                    if (path, ".".join(scopes[:i])) in symbols
                    and nodes[symbols[(path, ".".join(scopes[:i]))]].type == "Class"
                ),
                "",
            )
            if (path, owner_class + "." + ".".join(parts[1:])) in symbols:
                return symbols[(path, owner_class + "." + ".".join(parts[1:]))]
        # Instance assignment bindings, scoped to the caller.
        for i in range(len(scopes), -1, -1):
            prefix = ".".join(scopes[:i])
            for length in range(len(parts) - 1, 0, -1):
                receiver = ".".join(parts[:length])
                binding = p.bindings.get(f"{prefix}:{receiver}")
                if not binding and receiver.startswith(("self.", "this.")):
                    binding = p.bindings.get(f"{prefix}.__init__:{receiver}") or p.bindings.get(
                        f"{prefix}.constructor:{receiver}"
                    )
                if binding:
                    cls = resolve(p, binding, prefix, seen.copy())
                    if cls:
                        n = nodes[cls]
                        q = n.qualified_name.split(":", 1)[-1] + "." + ".".join(parts[length:])
                        if (n.file_path, q) in symbols:
                            return symbols[(n.file_path, q)]
        if any(f"{'.'.join(scopes[:length])}:{parts[0]}" in p.shadowed for length in range(len(scopes), -1, -1)):
            return None
        if parts[0] in p.imports:
            module, imported = p.imports[parts[0]]
            target_path = module_path(path, module)
            # from package import module
            if not target_path and imported != "*":
                target_path = module_path(path, module + "." + imported)
                if target_path:
                    imported = "*"
            if target_path:
                other = by_file[target_path]
                suffix = parts[1:]
                name = ".".join(([imported] if imported not in {"*", "default"} else []) + suffix)
                if imported == "default":
                    defaults = [
                        n
                        for n in other.symbols
                        if n.exported
                        and "export default"
                        in other.node.source[
                            max(0, other.node.source.find(n.source) - 30) : other.node.source.find(n.source) + 15
                        ]
                    ]
                    if len(defaults) == 1:
                        name = defaults[0].name + (("." + ".".join(suffix)) if suffix else "")
                if not name:
                    return other.node.id
                return resolve(other, name, "", seen)
        return None

    for p in parsed:
        path = p.node.file_path
        for alias, (module, imported) in p.imports.items():
            target_path = module_path(path, module)
            if not target_path:
                target_path = module_path(path, module + "." + imported)
            line = p.import_lines.get(alias, 1)
            if target_path:
                edge(p.node.id, by_file[target_path].node.id, "IMPORTS", path, line)
                symbol = resolve(p, alias)
                if symbol and symbol != by_file[target_path].node.id:
                    edge(p.node.id, symbol, "REFERENCES", path, line)
            else:
                is_local = module.startswith(".")
                name = (
                    module.split(".")[0]
                    if path.endswith(".py")
                    else "/".join(module.split("/")[:2])
                    if module.startswith("@")
                    else module.split("/")[0]
                )
                if not name:
                    name = module
                id = stable_id(repository_id, "unresolved-module" if is_local else "package", name)
                add(
                    CodeNode(
                        id=id,
                        name=name,
                        type="Module" if is_local else "ExternalPackage",
                        repository_id=repository_id,
                        qualified_name=module,
                    )
                )
                edge(
                    p.node.id,
                    id,
                    "IMPORTS" if is_local else "USES_PACKAGE",
                    path,
                    line,
                    "unresolved" if is_local else "resolved",
                )
        for ref in p.references:
            resolved = ref.target if ref.kind == "DEFINES" else resolve(p, ref.target, ref.scope)
            if resolved:
                edge(ref.owner, resolved, ref.kind, path, ref.line)
            else:
                id = stable_id(repository_id, path, ref.scope, "unresolved", ref.target)
                add(
                    CodeNode(
                        id=id,
                        name=ref.target,
                        type="UnresolvedSymbol",
                        repository_id=repository_id,
                        file_path=path,
                        start_line=ref.line,
                        end_line=ref.line,
                        qualified_name=ref.target,
                        module=p.node.module,
                    )
                )
                edge(ref.owner, id, ref.kind, path, ref.line, "unresolved")
            if ref.kind == "CALLS":
                imported_root = ref.target.split(".")[0]
                if imported_root in p.imports:
                    module, _ = p.imports[imported_root]
                    if not module.startswith(".") and not module_path(path, module):
                        package_name = (
                            module.split(".")[0]
                            if path.endswith(".py")
                            else "/".join(module.split("/")[:2])
                            if module.startswith("@")
                            else module.split("/")[0]
                        )
                        package_id = stable_id(repository_id, "package", package_name)
                        if package_id in nodes:
                            edge(ref.owner, package_id, "USES_PACKAGE", path, ref.line)
            # ORM entities have explicit model declarations, never inferred from generic variable names.
            if ref.kind in {"EXTENDS", "IMPLEMENTS"} and re.search(r"(?:^|\.)(Model|Base|Document)$", ref.target):
                owner = nodes[ref.owner]
                entity = owner.model_copy(update={"id": stable_id(owner.id, "entity"), "type": "DatabaseEntity"})
                add(entity)
                edge(owner.id, entity.id, "BELONGS_TO", path, ref.line, method="orm-pattern")
        for endpoint, handler in p.endpoints:
            target = resolve(p, handler)
            if target:
                edge(endpoint.id, target, "HANDLES", path, endpoint.start_line)
            else:
                id = stable_id(repository_id, path, "handler", handler)
                add(
                    CodeNode(
                        id=id,
                        name=handler,
                        type="UnresolvedSymbol",
                        repository_id=repository_id,
                        file_path=path,
                        start_line=endpoint.start_line,
                        end_line=endpoint.end_line,
                    )
                )
                edge(endpoint.id, id, "HANDLES", path, endpoint.start_line, "unresolved")
    # A second pass sees model entities regardless of source-file order.
    entity_for = {e.source: e.target for e in edges.values() if e.type == "BELONGS_TO"}
    for p in parsed:
        for ref in p.references:
            if ref.kind != "CALLS":
                continue
            bits = ref.target.split(".")
            operation = bits[-1]
            if operation not in {
                "create",
                "save",
                "update",
                "delete",
                "add",
                "insert",
                "insert_one",
                "find",
                "find_one",
                "filter",
                "get",
                "all",
                "select",
                "query",
            }:
                continue
            model_names = [bits[0]] + re.findall(r"\b[A-Z]\w*\b", ref.arguments)
            for model in model_names:
                id = resolve(p, model, ref.scope)
                if id in entity_for:
                    kind = (
                        "WRITES_TO"
                        if operation in {"create", "save", "update", "delete", "add", "insert", "insert_one"}
                        else "READS_FROM"
                    )
                    edge(ref.owner, entity_for[id], kind, p.node.file_path, ref.line, "probable", "orm-pattern")
    fingerprint = stable_id(
        *(p.node.file_path + ":" + p.node.hash for p in sorted(parsed, key=lambda p: p.node.file_path))
    )
    return CodeGraph(nodes=list(nodes.values()), edges=list(edges.values()), warnings=warnings, fingerprint=fingerprint)
