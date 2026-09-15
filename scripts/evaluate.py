#!/usr/bin/env python3
"""Live, repeatable demo evaluation. No paid AI provider is needed.
Run: backend/.venv/bin/python scripts/evaluate.py --api http://localhost:8000
"""
import argparse
import json
import time
from pathlib import Path
import httpx

GROUND_TRUTH = [
    {"question":"JWT signature validation", "expected":["utils/tokens.py:verify_token"]},
    {"question":"charge a credit card through the payment provider", "expected":["services/payments.py:PaymentService.process_payment","services/provider.py:StripeClient.charge"]},
    {"question":"customer account password verification", "expected":["services/users.py:UserService.check_password"]},
    {"question":"persist checkout order to database", "expected":["services/orders.py:OrderService.checkout"]},
    {"question":"establish a database session", "expected":["models/database.py:get_session"]},
]
DEPENDENCIES = [
    ("api/routes.py:checkout","services/orders.py:OrderService.checkout"),
    ("services/orders.py:OrderService.checkout","services/payments.py:PaymentService.process_payment"),
    ("services/auth.py:AuthService.authenticate","utils/tokens.py:verify_token"),
    ("web/checkout.ts:submitCheckout","web/client.ts:ApiClient.checkout"),
]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--api",default="http://localhost:8000")
    parser.add_argument("--repository")
    parser.add_argument("--output",default="evaluation-results.json")
    parser.add_argument("--skip-answers",action="store_true")
    args=parser.parse_args()
    with httpx.Client(base_url=args.api,timeout=600) as client:
        def get(endpoint,**params):
            response=client.get('/api'+endpoint,params=params)
            response.raise_for_status()
            return response.json()
        def post(path,data=None):
            response=client.post('/api'+path,json=data)
            response.raise_for_status()
            return response.json()
        id=args.repository or post('/repositories/demo')["id"]
        base='/repositories/'+id
        deadline=time.monotonic()+1800
        status=None
        while True:
            repo=get(base+'/status')
            if repo["status"]!=status:
                print(repo["status"],repo["message"],flush=True)
                status=repo["status"]
            if status=="READY":break
            if status=="FAILED" or time.monotonic()>deadline:raise RuntimeError(repo["message"])
            time.sleep(2)
        graph=get(base+'/graph',view='symbols',limit=500)
        nodes={n["id"]:n for n in graph["nodes"]}
        names={n["qualified_name"]:n["id"] for n in graph["nodes"]}
        retrieval=[]
        for case in GROUND_TRUTH:
            results=get(base+'/search',q=case["question"],mode='semantic',top_k=5)
            returned=[n["qualified_name"] for n in results["results"]]
            retrieval.append({**case,"returned":returned,"hit":any(n in returned for n in case["expected"]),"warning":results.get("warning")})
        actual={(nodes[e["source"]]["qualified_name"],nodes[e["target"]]["qualified_name"]) for e in graph["edges"] if e["type"]=='CALLS' and e["resolution"]=='resolved'}
        dependencies=[{"source":a,"target":b,"correct":(a,b) in actual} for a,b in DEPENDENCIES]
        endpoint=next(n["id"] for n in nodes.values() if n["name"]=='POST /checkout')
        payment=names['services/payments.py:PaymentService.process_payment']
        entity=next(n["id"] for n in nodes.values() if n["name"]=='Order' and n["type"]=='DatabaseEntity')
        path_checks=[]
        edge_pairs={(e["source"],e["target"]) for e in graph["edges"] if e["resolution"]!='unresolved'}
        for target in [payment,entity]:
            path=get(base+'/paths',source_id=endpoint,target_id=target)["path"]
            correct=len(path)==4 and path[0]==endpoint and path[-1]==target and all((a,b) in edge_pairs for a,b in zip(path,path[1:]))
            path_checks.append({"target":nodes[target]["name"],"path":path,"correct":correct})
        answers=[]
        if not args.skip_answers:
            for question in ["What could break if I modify verify_token?","Trace POST /checkout to the database."]:
                print('Asking:',question,flush=True)
                answer=post(base+'/ask',{"question":question})
                valid=[]
                for citation in answer["citations"]:
                    source=get(base+'/source',path=citation['file'])
                    node=nodes.get(citation['symbol_id'])
                    valid.append(bool(node and node['file_path']==citation['file'] and 1<=citation['start_line']<=citation['end_line']<=source['end_line']))
                supported_paths=all(all((a,b) in edge_pairs for a,b in zip(path,path[1:])) for path in answer['paths'])
                answers.append({"question":question,"answer":answer['answer'],"grounding":answer['grounding'],"citation_correctness":sum(valid)/max(1,len(valid)),"evidence_coverage":bool(answer['citations']) and all(s in nodes for s in answer['symbols']),"paths_supported":supported_paths,"tools":len(answer['tool_calls'])})
        metrics={"retrieval_hit_rate_at_5":sum(c['hit'] for c in retrieval)/len(retrieval),"known_dependency_recall":sum(c['correct'] for c in dependencies)/len(dependencies),"path_accuracy":sum(c['correct'] for c in path_checks)/len(path_checks),"citation_correctness":sum(c['citation_correctness'] for c in answers)/len(answers) if answers else None,"answer_evidence_coverage":sum(c['evidence_coverage'] and c['paths_supported'] for c in answers)/len(answers) if answers else None,"llm_answer_count":sum(c['grounding']=='llm-with-evidence' for c in answers)}
        report={"repository":id,"metrics":metrics,"retrieval":retrieval,"dependencies":dependencies,"paths":path_checks,"answers":answers,"limitations":"Small curated ground truth. Evidence coverage checks citation identities and graph paths, not the semantic truth of every generated sentence. Dependency metric is recall on known edges, not precision over the entire graph."}
        Path(args.output).write_text(json.dumps(report,indent=2))
        print(json.dumps(metrics,indent=2))
        if metrics['known_dependency_recall']<1 or metrics['path_accuracy']<1 or metrics['retrieval_hit_rate_at_5']<0.6:
            raise SystemExit('Evaluation below the documented acceptance threshold')

if __name__=='__main__':main()
