"""Tree-sitter adapters. Syntax gives symbols; conservative bindings resolve targets."""

import ast
from bisect import bisect_right
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from tree_sitter import Language, Parser
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
from app.models.schema import CodeNode, stable_id


@dataclass
class Reference:
    owner: str
    target: str
    kind: str
    line: int
    scope: str = ""
    arguments: str = ""


@dataclass
class ParsedFile:
    node: CodeNode
    symbols: list[CodeNode] = field(default_factory=list)
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)
    import_lines: dict[str, int] = field(default_factory=dict)
    references: list[Reference] = field(default_factory=list)
    bindings: dict[str, str] = field(default_factory=dict)
    endpoints: list[tuple[CodeNode, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reexports: dict[str, tuple[str, str]] = field(default_factory=dict)
    shadowed: set[str] = field(default_factory=set)
    assignments: set[str] = field(default_factory=set)


class TreeSitterAnalyzer:
    language = ""
    grammar = None
    function_types = {
        "function_definition",
        "function_declaration",
        "generator_function_declaration",
        "method_definition",
        "method_signature",
        "arrow_function",
        "function_expression",
    }
    class_types = {"class_definition", "class_declaration", "abstract_class_declaration", "interface_declaration"}

    def __init__(self):
        self.parser = Parser(Language(self.grammar()))

    def analyze(self, repository_id: str, path: str, source: str) -> ParsedFile:
        raw = source.encode()
        tree = self.parser.parse(raw)
        root = tree.root_node
        # tree-sitter 0.26.0 has a Point reference-count bug (#500).
        # Derive source positions from byte offsets; do not instantiate Point objects.
        line_offsets = [0] + [index + 1 for index, byte in enumerate(raw) if byte == 10]

        def line(node):
            return bisect_right(line_offsets, node.start_byte)

        def end_line(node):
            return bisect_right(line_offsets, node.end_byte)

        def column(node):
            return node.start_byte - line_offsets[line(node) - 1]

        module = str(PurePosixPath(path).parent)
        if module == ".":
            module = "root"
        file = CodeNode(
            id=stable_id(repository_id, path),
            name=PurePosixPath(path).name,
            type="File",
            repository_id=repository_id,
            qualified_name=path,
            file_path=path,
            language=self.language,
            end_line=max(1, len(source.splitlines())),
            source=source,
            hash=stable_id(source),
            module=module,
        )
        result = ParsedFile(file)
        controller_prefixes = {}
        self.extract_imports(source, root, result)
        if root.has_error:
            result.warnings.append(f"{path}: syntax errors; only recognized syntax was extracted")

        def text(node):
            return raw[node.start_byte : node.end_byte].decode() if node else ""

        def field_text(node, name):
            return text(node.child_by_field_name(name))

        def add_route(method, route, handler, line, end_line, snippet):
            name = f"{method.upper()} {route}"
            endpoint = CodeNode(
                id=stable_id(repository_id, path, name, str(line)),
                name=name,
                qualified_name=name,
                type="Endpoint",
                repository_id=repository_id,
                file_path=path,
                language=self.language,
                start_line=line,
                end_line=end_line,
                source=snippet,
                signature=name,
                module=module,
            )
            result.endpoints.append((endpoint, handler))

        def walk(node, owner=file, scope="", class_name=""):
            t = node.type
            current_owner, current_scope, current_class = owner, scope, class_name
            if t in self.class_types | self.function_types:
                name = field_text(node, "name")
                if (
                    not name
                    and node.parent
                    and node.parent.type in {"variable_declarator", "assignment", "pair", "public_field_definition"}
                ):
                    name = (
                        field_text(node.parent, "name")
                        or field_text(node.parent, "left")
                        or field_text(node.parent, "key")
                    )
                if not name and t in self.function_types:
                    name = f"callback@{line(node)}:{column(node)}"
                if name:
                    is_class = t in self.class_types
                    kind = (
                        "Interface"
                        if t == "interface_declaration"
                        else "Class"
                        if is_class
                        else "Method"
                        if owner.type in {"Class", "Interface"}
                        else "Function"
                    )
                    qualified = f"{scope}.{name}".strip(".")
                    parameters = field_text(node, "parameters")
                    body = node.child_by_field_name("body")
                    signature = text(node)[: (body.start_byte - node.start_byte) if body else 250].strip().rstrip(":{")
                    snippet = text(node)
                    doc = ""
                    if body and body.named_children and body.named_children[0].type == "expression_statement":
                        expr = body.named_children[0]
                        if expr.named_children and expr.named_children[0].type == "string":
                            doc = text(expr).strip("\"'")
                    previous = node.prev_named_sibling
                    if previous and previous.type == "comment":
                        doc = text(previous)
                    symbol = CodeNode(
                        id=stable_id(repository_id, path, qualified, kind),
                        name=name,
                        qualified_name=f"{path}:{qualified}",
                        type=kind,
                        repository_id=repository_id,
                        file_path=path,
                        language=self.language,
                        start_line=line(node),
                        end_line=end_line(node),
                        signature=signature,
                        source=snippet,
                        docstring=doc,
                        parameters=parameters,
                        returns=field_text(node, "return_type"),
                        hash=stable_id(snippet),
                        module=module,
                        exported=(node.parent.type == "export_statement" if node.parent else False),
                    )
                    result.symbols.append(symbol)
                    params_node = node.child_by_field_name("parameters")
                    if params_node and not is_class:
                        for param in params_node.named_children:
                            param_name = (
                                text(param)
                                if param.type == "identifier"
                                else field_text(param, "name") or field_text(param, "pattern")
                            )
                            if not param_name and param.named_children:
                                param_name = text(param.named_children[0])
                            if re.fullmatch(r"[A-Za-z_$][\w$]*", param_name or ""):
                                result.shadowed.add(f"{qualified}:{param_name}")
                    result.references.append(Reference(owner.id, symbol.id, "DEFINES", symbol.start_line))
                    current_owner, current_scope = symbol, qualified
                    if is_class:
                        current_class = qualified
                        bases = field_text(node, "superclasses")
                        for child in node.named_children:
                            if child.type in {"class_heritage", "extends_type_clause"}:
                                bases += " " + text(child)
                        for base in re.findall(r"[A-Za-z_$][\w.$]*", bases):
                            if base not in {"extends", "implements"}:
                                kind_rel = (
                                    "IMPLEMENTS"
                                    if "implements" in bases and base in bases.split("implements", 1)[1]
                                    else "EXTENDS"
                                )
                                result.references.append(Reference(symbol.id, base, kind_rel, symbol.start_line, scope))
                    # FastAPI / Flask decorators and NestJS method decorators.
                    decorators = (
                        text(node.parent)[: node.start_byte - node.parent.start_byte]
                        if node.parent and node.parent.type in {"decorated_definition", "export_statement"}
                        else ""
                    )
                    if node.prev_named_sibling and node.prev_named_sibling.type == "decorator":
                        decorators += text(node.prev_named_sibling)
                    decorators += "\n".join(text(c) for c in node.named_children if c.type == "decorator")
                    controller = re.search(r"@Controller\(\s*['\"]([^'\"]*)['\"]", decorators)
                    if controller and symbol.type == "Class":
                        controller_prefixes[qualified] = controller[1]
                    for match in re.finditer(
                        r"@(?:[\w.]+\.)?(get|post|put|patch|delete|route|Get|Post|Put|Patch|Delete)\(\s*['\"]([^'\"]*)['\"]([^)]*)\)",
                        decorators,
                    ):
                        verb, route, rest = match.groups()
                        if verb[0].isupper():
                            route = "/" + "/".join(
                                part.strip("/")
                                for part in [controller_prefixes.get(class_name, ""), route]
                                if part.strip("/")
                            )
                        methods = (
                            re.findall(r"['\"](GET|POST|PUT|PATCH|DELETE)['\"]", rest) if verb == "route" else [verb]
                        )
                        for method in methods or ["GET"]:
                            add_route(
                                method, route, symbol.id, line(node.parent), symbol.start_line, decorators.strip()
                            )
                    if (
                        self.language == "TypeScript"
                        and PurePosixPath(path).name in {"route.ts", "route.tsx"}
                        and name in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                    ):
                        route = "/" + "/".join(p for p in PurePosixPath(path).parts[1:-1] if not p.startswith("("))
                        add_route(name, route, symbol.id, symbol.start_line, symbol.end_line, signature)
            if t in {"assignment", "variable_declarator", "public_field_definition"}:
                lhs = field_text(node, "left") or field_text(node, "name")
                rhs = node.child_by_field_name("right") or node.child_by_field_name("value")
                binding_key = f"{scope}:{lhs}"
                repeated = binding_key in result.assignments
                if lhs:
                    result.assignments.add(binding_key)
                    if not rhs or rhs.type not in self.function_types or repeated:
                        result.shadowed.add(binding_key)
                if repeated:
                    result.bindings.pop(binding_key, None)
                if not repeated and rhs and rhs.type in {"call", "call_expression", "new_expression"}:
                    target = field_text(rhs, "function") or field_text(rhs, "constructor")
                    if lhs and target:
                        result.bindings[f"{scope}:{lhs}"] = target
                # TypeScript annotated parameters/fields are handled below.
            if t in {"required_parameter", "optional_parameter", "typed_parameter"}:
                annotation = field_text(node, "type").lstrip(": ")
                param = field_text(node, "pattern") or field_text(node, "name")
                if not param and node.named_children:
                    param = text(node.named_children[0])
                if param and re.fullmatch(r"[\w.]+", annotation):
                    result.bindings[f"{scope}:{param}"] = annotation
            if t in {"call", "call_expression", "new_expression"}:
                target = field_text(node, "function") or field_text(node, "constructor")
                arguments = field_text(node, "arguments")
                if target:
                    result.references.append(Reference(owner.id, target, "CALLS", line(node), scope, arguments))
                    if target.split(".")[-1] in {"Depends", "Security"}:
                        dependency = re.match(r"\(\s*([\w.]+)\s*[,)]", arguments)
                        if dependency:
                            result.references.append(
                                Reference(owner.id, dependency[1], "DEPENDS_ON", line(node), scope)
                            )
                    route_match = re.fullmatch(r"[\w.]+\.(get|post|put|patch|delete|use|all)", target)
                    args_node = node.child_by_field_name("arguments")
                    args = args_node.named_children if args_node else []
                    receiver = target.rsplit(".", 1)[0]
                    router_binding = result.bindings.get(f":{receiver}", "")
                    imported_router = result.imports.get(router_binding.split(".")[0], ("", ""))[0] == "express"
                    if (
                        route_match
                        and self.language != "Python"
                        and imported_router
                        and len(args) >= 2
                        and args[0].type in {"string", "string_literal"}
                    ):
                        route = text(args[0]).strip("\"'")
                        handler = args[-1]
                        handler_name = (
                            text(handler)
                            if handler.type in {"identifier", "member_expression"}
                            else f"callback@{line(handler)}:{column(handler)}"
                        )
                        add_route(route_match[1], route, handler_name, line(node), end_line(node), text(node))
                    if target in {"path", "re_path"} and len(args) >= 2 and args[0].type == "string":
                        add_route(
                            "ANY",
                            "/" + text(args[0]).strip("\"'").lstrip("/"),
                            text(args[1]).removesuffix(".as_view()"),
                            line(node),
                            end_line(node),
                            text(node),
                        )
            for child in node.named_children:
                walk(child, current_owner, current_scope, current_class)

        walk(root)
        return result

    def extract_imports(self, source, root, result):
        raw = source.encode()

        def line(node):
            return raw.count(b"\n", 0, node.start_byte) + 1

        def walk(node):
            snippet = raw[node.start_byte : node.end_byte].decode()
            if node.type in {"import_statement", "export_statement"}:
                match = re.search(r"(?:from\s*|^import\s*)['\"]([^'\"]+)['\"]", snippet)
                if match:
                    module = match[1]
                    names = re.search(r"\{([^}]+)\}", snippet)
                    if names:
                        for part in names[1].split(","):
                            pair = re.split(r"\s+as\s+", part.strip().removeprefix("type "))
                            if pair[0]:
                                local = pair[-1]
                                result.imports[local] = (module, pair[0])
                                result.import_lines[local] = line(node)
                                if node.type == "export_statement":
                                    result.reexports[local] = (module, pair[0])
                    default = re.match(r"import\s+(\w+)(?:\s*,|\s+from)", snippet)
                    namespace = re.search(r"\*\s+as\s+(\w+)", snippet)
                    if default or namespace:
                        local = (default or namespace)[1]
                        result.imports[local] = (module, "default" if default else "*")
                        result.import_lines[local] = line(node)
                    if not names and not default and not namespace:
                        result.imports[module] = (module, "*")
                        result.import_lines[module] = line(node)
            # CommonJS const x = require('./x')
            if node.type == "variable_declarator":
                match = re.match(r"(\w+)\s*=\s*require\(['\"]([^'\"]+)['\"]\)", snippet)
                if match:
                    result.imports[match[1]] = (match[2], "*")
                    result.import_lines[match[1]] = line(node)
            for child in node.named_children:
                walk(child)

        walk(root)


class PythonAnalyzer(TreeSitterAnalyzer):
    language = "Python"
    grammar = staticmethod(tree_sitter_python.language)

    def extract_imports(self, source, root, result):
        # Python's standard AST enriches Tree-sitter extraction with exact alias semantics.
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                for alias in node.names:
                    local = alias.asname or alias.name
                    result.imports[local] = (module, alias.name)
                    result.import_lines[local] = node.lineno
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    result.imports[local] = (alias.name if alias.asname else local, "*")
                    result.import_lines[local] = node.lineno


class JavaScriptAnalyzer(TreeSitterAnalyzer):
    language = "JavaScript"
    grammar = staticmethod(tree_sitter_javascript.language)


class TypeScriptAnalyzer(TreeSitterAnalyzer):
    language = "TypeScript"
    grammar = staticmethod(tree_sitter_typescript.language_typescript)


class TSXAnalyzer(TypeScriptAnalyzer):
    grammar = staticmethod(tree_sitter_typescript.language_tsx)


ADAPTERS = {
    ".py": PythonAnalyzer,
    ".js": JavaScriptAnalyzer,
    ".jsx": JavaScriptAnalyzer,
    ".mjs": JavaScriptAnalyzer,
    ".cjs": JavaScriptAnalyzer,
    ".ts": TypeScriptAnalyzer,
    ".tsx": TSXAnalyzer,
}
