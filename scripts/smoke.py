#!/usr/bin/env python3
"""Exercise real upload and GitHub ingestion through HTTP, never direct DB seeding."""
import io
import json
import time
import zipfile
import httpx

with httpx.Client(base_url='http://localhost:8000/api',timeout=600) as client:
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('fixture/service.py','def validate_token(token: str):\n    """Validate authentication credentials."""\n    return bool(token)\n')
        z.writestr('fixture/api.py','from service import validate_token\n\ndef authenticate(token):\n    return validate_token(token)\n')
    upload=client.post('/repositories/upload',files={'file':('smoke-fixture.zip',archive.getvalue(),'application/zip')})
    upload.raise_for_status()
    github=client.post('/repositories/github',json={'url':'https://github.com/pallets/itsdangerous'})
    github.raise_for_status()
    repositories=[upload.json(),github.json()]
    for initial in repositories:
        id=initial['id']
        previous=None
        deadline=time.monotonic()+1800
        while time.monotonic()<deadline:
            status=client.get('/repositories/'+id+'/status').json()
            if status['status']!=previous:
                print(initial['name'],status['status'],status['message'],flush=True)
                previous=status['status']
            if status['status']=='FAILED':raise RuntimeError(status['message'])
            if status['status']=='READY':break
            time.sleep(2)
        else:raise RuntimeError('Ingestion timed out')
        base='/repositories/'+id
        for path in ['/graph','/overview','/files']:
            response=client.get(base+path)
            response.raise_for_status()
        overview=client.get(base+'/overview').json()
        assert overview['files']>0 and overview['relationships']>0
        result=client.get(base+'/search',params={'q':'authentication security','mode':'semantic'}).json()
        assert result['results'],result
        print(json.dumps({'repository':id,'name':initial['name'],'files':overview['files'],'nodes':overview['nodes'],'semantic_results':len(result['results'])}),flush=True)
    print('ZIP and GitHub ingestion smoke checks passed.')
