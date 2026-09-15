from conftest import symbol, triples


def test_python_cross_file_aliases_and_inheritance(parse):
    graph = parse(
        {
            "services/auth.py": "def verify_token(token: str) -> bool:\n    return bool(token)\n\nclass Base:\n    def valid(self):\n        return True\n",
            "main.py": "from services.auth import verify_token as verify, Base\nclass Auth(Base):\n    def run(self, token):\n        return verify(token)\n",
        }
    )
    assert ("main.py:Auth.run", "services/auth.py:verify_token") in triples(graph)
    assert ("main.py:Auth", "services/auth.py:Base") in triples(graph, "EXTENDS")
    assert symbol(graph, "verify_token").returns == "bool"


def test_methods_self_and_instance_assignment(parse):
    graph = parse(
        {
            "app.py": "class Service:\n    def execute(self):\n        return self.validate()\n    def validate(self):\n        return True\n\ndef entry():\n    svc = Service()\n    return svc.execute()\n"
        }
    )
    assert ("app.py:Service.execute", "app.py:Service.validate") in triples(graph)
    assert ("app.py:entry", "app.py:Service.execute") in triples(graph)


def test_unresolved_does_not_match_same_name_elsewhere(parse):
    graph = parse({"a.py": "def missing():\n    return 1\n", "b.py": "def caller():\n    return missing()\n"})
    e = next(e for e in graph.edges if e.type == "CALLS")
    assert e.resolution == "unresolved"
    assert next(n for n in graph.nodes if n.id == e.target).type == "UnresolvedSymbol"


def test_fastapi_route_and_dependency(parse):
    graph = parse(
        {
            "api.py": "from fastapi import FastAPI, Depends\napp=FastAPI()\ndef auth():\n    return True\n@app.post('/checkout')\ndef checkout(user=Depends(auth)):\n    return user\n"
        }
    )
    endpoint = symbol(graph, "POST /checkout")
    handler = symbol(graph, "checkout")
    assert any(e.source == endpoint.id and e.target == handler.id and e.type == "HANDLES" for e in graph.edges)
    assert ("api.py:checkout", "api.py:auth") in triples(graph, "DEPENDS_ON")


def test_flask_and_django_routes(parse):
    graph = parse(
        {
            "routes.py": "from flask import Flask\nfrom django.urls import path\napp=Flask(__name__)\n@app.route('/users', methods=['GET','POST'])\ndef users():\n    return []\nurlpatterns=[path('customers/', users)]\n"
        }
    )
    assert {"GET /users", "POST /users", "ANY /customers/"} <= {n.name for n in graph.nodes if n.type == "Endpoint"}


def test_typescript_alias_and_methods(parse):
    graph = parse(
        {
            "service.ts": "export class Service { run(): number { return 1; } }\nexport interface Shape { run(): number; }",
            "app.ts": "import { Service as Worker } from './service';\nconst worker = new Worker();\nexport const execute = () => worker.run();",
        }
    )
    assert ("app.ts:execute", "service.ts:Service.run") in triples(graph)
    assert symbol(graph, "Shape").type == "Interface"


def test_js_route_and_anonymous_callback(parse):
    graph = parse(
        {
            "app.js": "import express from 'express';\nconst router = express.Router();\nfunction users(req,res) { return res.json([]); }\nrouter.get('/users', users);\nrouter.post('/users', (req,res) => res.json({}));"
        }
    )
    endpoints = [n for n in graph.nodes if n.type == "Endpoint"]
    assert len(endpoints) == 2
    assert all(
        any(e.source == n.id and e.type == "HANDLES" and e.resolution == "resolved" for e in graph.edges)
        for n in endpoints
    )


def test_next_route_and_tsx(parse):
    graph = parse(
        {
            "app/api/users/route.ts": "export async function GET() { return Response.json([]); }",
            "app/page.tsx": "export default function Page() { return <main>Hello</main>; }",
        }
    )
    assert symbol(graph, "GET /api/users").type == "Endpoint"
    assert symbol(graph, "Page").type == "Function"


def test_fingerprint_and_ids_stable(parse):
    g1 = parse({"app.py": "def foo():\n    return 1\n"})
    g2 = parse({"app.py": "def foo():\n    return 2\n"})
    assert symbol(g1, "foo").id == symbol(g2, "foo").id
    assert g1.fingerprint != g2.fingerprint


def test_partial_syntax_reports_warning(parse):
    graph = parse({"broken.py": "def ok():\n    return 1\n\ndef broken(:\n    pass\n"})
    assert graph.warnings
    assert symbol(graph, "ok")


def test_no_phantom_orm_entities(parse):
    graph = parse({"app.py": "def run(db):\n    return db.get('users')\n"})
    assert not [n for n in graph.nodes if n.type == "DatabaseEntity"]


def test_nest_controller_prefix(parse):
    graph = parse(
        {
            "orders.ts": "import { Controller, Post } from '@nestjs/common';\n@Controller('orders')\nexport class OrderController {\n @Post('checkout')\n checkout() { return true; }\n}"
        }
    )
    assert symbol(graph, "POST /orders/checkout").type == "Endpoint"


def test_shadowed_import_is_unresolved(parse):
    graph = parse(
        {
            "lib.py": "def verify(): return True",
            "app.py": "from lib import verify\ndef run(verify):\n    return verify()",
        }
    )
    assert ("app.py:run", "lib.py:verify") not in triples(graph)


def test_reassigned_instance_does_not_keep_stale_type(parse):
    graph = parse(
        {
            "app.py": "class Service:\n    def run(self): return True\ndef entry(other):\n    svc=Service()\n    svc=other\n    return svc.run()"
        }
    )
    assert ("app.py:entry", "app.py:Service.run") not in triples(graph)


def test_large_tree_position_regression(parse):
    source = "\n".join(f"def fn_{i}(value):\n    return str(value)\n" for i in range(400))
    graph = parse({"large.py": source})
    assert len([n for n in graph.nodes if n.type == "Function"]) == 400
    assert symbol(graph, "fn_399").start_line == 1198


def test_dictionary_and_map_get_are_not_api_endpoints(parse):
    graph = parse(
        {
            "config.py": "def read(settings):\n    return settings.get('secret', None)\n",
            "config.js": "const m=new Map();\nm.get('/users',fallback);",
        }
    )
    assert not [n for n in graph.nodes if n.type == "Endpoint"]
