"""Scoped P0 release over the recorded production image; no unrelated local source."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile
import boto3
from reading_aws import BUILD, REPO, ROOT, BUCKET, CLUSTER, PUBLIC, once

FRONTEND='paper-attribution-frontend-dev-247893369214'
FILES=('api/chat.py','api/reader_auth.py','api/access.py','models/access.py',
       'services/access_control.py','services/access_schema.py','services/paper_chat.py','services/chat_access.py')


def bundle(kind):
    if kind=='backend':
        with zipfile.ZipFile(BUILD/'p0-reading-before.zip') as z:
            files={n:z.read(n).decode() for n in z.namelist()}
        files.update({'app/'+p:(REPO/'backend/app'/p).read_text() for p in FILES})
        main=files['app/main.py']
        main=once(main,'app = FastAPI(', 'from app.services.access_control import authorize_route\nfrom app.api import access\n\napp = FastAPI(\n    dependencies=[Depends(authorize_route)],\n    docs_url=None, redoc_url=None, openapi_url=None,')
        main=once(main,'app.include_router(reading.router)', 'app.include_router(reading.router)\napp.include_router(access.router)')
        main=once(main,'if request.url.path.startswith(("/auth/", "/chat/", "/reading/")):', 'if request.url.path != "/health":')
        files['app/main.py']=main
        files['app/models/__init__.py']=once(files['app/models/__init__.py'],'all_models = (','from app.models.access import AdminGrant, AccessAudit\n\nall_models = (\n    AdminGrant, AccessAudit,')
        files['paper_monitor/access_smoke.py']=(ROOT/'paper_monitor/access_smoke.py').read_text()
    else:
        files={'app/'+p:(REPO/'backend/app'/p).read_text() for p in ('institution_main.py','services/institution_access.py')}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        for path,value in sorted(files.items()):
            compile(value,path,'exec');archive.writestr(zipfile.ZipInfo(path,date_time=(2026,1,1,0,0,0)),value)
    return out.getvalue(),files


def prepare_assets(s3):
    if (BUILD/'p0-assets-manifest.json').exists():
        raise RuntimeError('The original frontend snapshot already exists. Do not overwrite it with the access shell.')
    manifest=[]
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=FRONTEND):
        for row in page.get('Contents',[]):
            key=row['Key']
            if key.startswith(('reading/','protected-legacy/')):continue
            target='protected-legacy/'+key
            if key.endswith('.html') or '.' not in key.rsplit('/',1)[-1]:
                raw=s3.get_object(Bucket=FRONTEND,Key=key)['Body'].read()
                if b'<head>' in raw:
                    raw=raw.replace(b'<head>',b'<head><script src="/reading/access-guard.js"></script>',1)
                s3.put_object(Bucket=FRONTEND,Key=target,Body=raw,ContentType='text/html',CacheControl='private,no-store',ServerSideEncryption='AES256')
            else:
                s3.copy_object(Bucket=FRONTEND,Key=target,CopySource={'Bucket':FRONTEND,'Key':key})
            manifest.append({'key':key,'size':row['Size']})
    (BUILD/'p0-assets-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'protected_snapshot_files':len(manifest),'bytes':sum(r['size'] for r in manifest)}))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['backend','institution','assets']);parser.add_argument('--apply',action='store_true');parser.add_argument('--promote',action='store_true');args=parser.parse_args()
    aws=boto3.Session(profile_name='pas-sdl0-dev',region_name='ca-central-1');ecs=aws.client('ecs')
    if args.kind=='assets':
        if not args.apply:raise SystemExit('Use --apply to snapshot the current frontend before publishing the gate.')
        prepare_assets(aws.client('s3'));return
    baseline=json.loads((BUILD/f'p0-{args.kind}-before.json').read_text());before=baseline['task'];service=baseline['service']
    data,files=bundle(args.kind);sha=hashlib.sha256(data).hexdigest();key=f'author-monitor/access/releases/{sha}.zip'
    record=BUILD/f'p0-{args.kind}-release.json'
    svc=ecs.describe_services(cluster=CLUSTER,services=[service['serviceName']])['services'][0]
    if args.promote:
        release=json.loads(record.read_text());assert sha==release['sha256'];assert svc['taskDefinition']==release['previous']
        task=ecs.describe_tasks(cluster=CLUSTER,tasks=[release['canary']])['tasks'][0]
        if args.kind=='backend':assert task['lastStatus']=='STOPPED' and task['containers'][0].get('exitCode')==0
        else:assert task['lastStatus']=='STOPPED' and task['containers'][0].get('exitCode')==0
        ecs.update_service(cluster=CLUSTER,service=service['serviceName'],taskDefinition=release['task_definition'])
        print(json.dumps({'promoted':release['task_definition']}));return
    print(json.dumps({'kind':args.kind,'sha256':sha,'files':list(files)}))
    if not args.apply:return
    previous_release=json.loads(record.read_text()) if record.exists() else {}
    assert svc['taskDefinition'] in (before['taskDefinitionArn'], previous_release.get('task_definition'))
    aws.client('s3').put_object(Bucket=BUCKET,Key=key,Body=data,ServerSideEncryption='AES256')
    statements=[{'Effect':'Allow','Action':'s3:GetObject','Resource':f'arn:aws:s3:::{BUCKET}/author-monitor/access/releases/*'}]
    if args.kind=='backend':statements.append({'Effect':'Allow','Action':'s3:GetObject','Resource':f'arn:aws:s3:::{FRONTEND}/protected-legacy/*'})
    aws.client('iam').put_role_policy(RoleName=before['taskRoleArn'].rsplit('/',1)[-1],PolicyName='PASAccessControl',PolicyDocument=json.dumps({'Version':'2012-10-17','Statement':statements}))
    allowed=ecs.meta.service_model.operation_model('RegisterTaskDefinition').input_shape.members
    task={k:copy.deepcopy(v) for k,v in before.items() if k in allowed};c=task['containerDefinitions'][0]
    env={e['name']:e['value'] for e in c['environment']};env.update(P0_BUCKET=BUCKET,P0_KEY=key,P0_SHA256=sha)
    download="""
raw=boto3.client('s3').get_object(Bucket=os.environ['P0_BUCKET'],Key=os.environ['P0_KEY'])['Body'].read()
if hashlib.sha256(raw).hexdigest()!=os.environ['P0_SHA256']:raise RuntimeError('P0 checksum mismatch')
"""
    if args.kind=='backend':
        env['PAS_ADMIN_ASSETS_BUCKET']=FRONTEND
        script=before['containerDefinitions'][0]['command'][2].split('from app.db import Base,engine')[0]+download+"""
zipfile.ZipFile(io.BytesIO(raw)).extractall('/app')
from app.db import Base,engine,SessionLocal
from app.models import all_models
from app.services.reading_schema import ensure_reading_schema
from app.services.access_schema import ensure_access_schema
from app.services.access_control import bootstrap_admin
ensure_reading_schema(engine,Base.metadata)
ensure_access_schema(engine,Base.metadata)
with SessionLocal() as db:bootstrap_admin(db,'T012M3T3U01','U07K96PT5CL')
module='paper_monitor.access_smoke' if '--check' in sys.argv else 'app.scripts.serve'
os.execv(sys.executable,[sys.executable,'-m',module])
"""
        c['command']=['python','-c',script]
        override=['python','-c',script,'--check']
    else:
        env.update(PAS_AUTHORITY_URL=PUBLIC,PYTHONPATH='/tmp/p0:/app:/opt/site-packages')
        # Distroless keeps a read-only root. Only the verified overlay volume is writable.
        # Bootstrap needs ownership of the fresh volume; the server runs as 65532.
        task.setdefault('volumes',[]).append({'name':'p0-runtime'})
        c.setdefault('mountPoints',[]).append({'sourceVolume':'p0-runtime','containerPath':'/tmp/p0','readOnly':False})
        c['user']='0';c['entryPoint']=['/usr/bin/python3']
        script="import os,sys,io,hashlib,zipfile,shutil,boto3\n"+download+"""
shutil.copytree('/app/app','/tmp/p0/app',dirs_exist_ok=True)
zipfile.ZipFile(io.BytesIO(raw)).extractall('/tmp/p0')
os.setgid(65532);os.setuid(65532)
sys.path.insert(0,'/tmp/p0')
import uvicorn
if '--check' in sys.argv:
    import threading,time,urllib.request,urllib.error,json
    threading.Thread(target=lambda:uvicorn.run('app.institution_main:app',host='127.0.0.1',port=8000),daemon=True).start()
    for _ in range(30):
        try:
            response=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=1)
            if response.status==200:break
        except OSError:time.sleep(0.2)
    else:raise RuntimeError('Institution canary did not start')
    for path in ['/institution-authorship/options','/api/institution-authorship/report','/institution-authorship/export.csv']:
        try:urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=3);raise RuntimeError('Anonymous institution access')
        except urllib.error.HTTPError as error:assert error.code==401
    print(json.dumps({'institution_access_canary':'passed','anonymous_routes':3,'uid':os.getuid()}))
else:
    uvicorn.run('app.institution_main:app',host='0.0.0.0',port=8000)
"""
        c['command']=['-c',script];override=['-c',script,'--check']
    c['environment']=[{'name':k,'value':v} for k,v in env.items()]
    arn=ecs.register_task_definition(**task)['taskDefinition']['taskDefinitionArn']
    params={'cluster':CLUSTER,'taskDefinition':arn,'launchType':'FARGATE','networkConfiguration':service['networkConfiguration']}
    if override:params['overrides']={'containerOverrides':[{'name':c['name'],'command':override}]}
    run=ecs.run_task(**params);assert not run.get('failures')
    release={'previous':svc['taskDefinition'],'task_definition':arn,'canary':run['tasks'][0]['taskArn'],'sha256':sha,'files':{p:hashlib.sha256(v.encode()).hexdigest() for p,v in files.items()}}
    record.write_text(json.dumps(release,indent=2));print(json.dumps(release))


if __name__=='__main__':main()
