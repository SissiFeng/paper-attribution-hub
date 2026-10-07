"""Scoped P1 update on the verified P0 deployment, with real-data canary."""
import argparse
import copy
import hashlib
import io
import json
import zipfile
from reading_aws import BUILD, REPO, ROOT, BUCKET, CLUSTER, SERVICE, once, aws_session

FILES=('api/reading.py','api/research.py','api/catalog.py','api/chat.py','models/research.py',
       'services/chat_access.py','services/paper_chat.py','services/reading_evidence.py',
       'services/grounded_answer_service.py','services/access_control.py','services/research_access.py','services/research_schema.py')


def bundle():
    with zipfile.ZipFile(BUILD/'p1-before.zip') as archive:
        files={n:archive.read(n).decode() for n in archive.namelist()}
    files.update({'app/'+p:(REPO/'backend/app'/p).read_text() for p in FILES})
    files['app/main.py']=once(files['app/main.py'],'app.include_router(reading.router)', 'app.include_router(reading.router)\nfrom app.api import research, catalog\napp.include_router(research.router)\napp.include_router(catalog.router)')
    files['app/models/__init__.py']=once(files['app/models/__init__.py'],'all_models = (',
        'from app.models.research import ResearchProject, ProjectMember, ProjectPaper, ProjectDiscussion, Annotation, EvidenceComparison\n\nall_models = (\n    ResearchProject, ProjectMember, ProjectPaper, ProjectDiscussion, Annotation, EvidenceComparison,')
    files['paper_monitor/research_smoke.py']=(ROOT/'paper_monitor/research_smoke.py').read_text()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        for path,source in sorted(files.items()):
            compile(source,path,'exec');archive.writestr(zipfile.ZipInfo(path,date_time=(2026,1,1,0,0,0)),source)
    return output.getvalue(),files


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');ap.add_argument('--promote',action='store_true');args=ap.parse_args()
    aws=aws_session();ecs=aws.client('ecs');s3=aws.client('s3')
    svc=ecs.describe_services(cluster=CLUSTER,services=[SERVICE])['services'][0]
    snapshot=BUILD/'p1-before.json';record=BUILD/'p1-release.json'
    if not snapshot.exists() or not snapshot.stat().st_size:
        current=ecs.describe_task_definition(taskDefinition=svc['taskDefinition'])['taskDefinition']
        env={e['name']:e['value'] for e in current['containerDefinitions'][0]['environment']}
        raw=s3.get_object(Bucket=env['P0_BUCKET'],Key=env['P0_KEY'])['Body'].read()
        assert hashlib.sha256(raw).hexdigest()==env['P0_SHA256']
        (BUILD/'p1-before.zip').write_bytes(raw)
        snapshot.touch(mode=0o600);snapshot.write_text(json.dumps({'service':svc,'task':current},default=str))
    before=json.loads(snapshot.read_text());data,files=bundle();sha=hashlib.sha256(data).hexdigest()
    if args.promote:
        release=json.loads(record.read_text());assert release['sha256']==sha
        canary=ecs.describe_tasks(cluster=CLUSTER,tasks=[release['canary']])['tasks'][0]
        assert canary['taskDefinitionArn']==release['task_definition']
        assert canary['lastStatus']=='STOPPED' and canary['containers'][0].get('exitCode')==0
        assert svc['taskDefinition']==release['previous']
        ecs.update_service(cluster=CLUSTER,service=SERVICE,taskDefinition=release['task_definition'])
        print(json.dumps({'promoted':release['task_definition'],'sha256':sha}));return
    print(json.dumps({'sha256':sha,'updated_files':list(FILES)}))
    if not args.apply:return
    previous=json.loads(record.read_text()) if record.exists() else {}
    if svc['taskDefinition'] not in (before['task']['taskDefinitionArn'],previous.get('task_definition')):
        assert svc['taskDefinition']==previous.get('previous')
        failed=ecs.describe_tasks(cluster=CLUSTER,tasks=[previous['canary']])['tasks'][0]
        assert failed['lastStatus']=='STOPPED' and failed['containers'][0].get('exitCode',0)!=0
        (BUILD/('p1-failed-canary-'+previous['canary'].rsplit('/',1)[-1]+'.json')).write_text(json.dumps(previous,indent=2))
    # Use the existing narrowly scoped access release prefix and existing IAM grant.
    key=f'author-monitor/access/releases/p1-{sha}.zip'
    s3.put_object(Bucket=BUCKET,Key=key,Body=data,ServerSideEncryption='AES256')
    allowed=ecs.meta.service_model.operation_model('RegisterTaskDefinition').input_shape.members
    task={k:copy.deepcopy(v) for k,v in before['task'].items() if k in allowed};c=task['containerDefinitions'][0]
    env={e['name']:e['value'] for e in c['environment']};env.update(P0_BUCKET=BUCKET,P0_KEY=key,P0_SHA256=sha)
    c['environment']=[{'name':k,'value':v} for k,v in env.items()]
    script=c['command'][2]
    script=once(script,"module='paper_monitor.access_smoke'", "from app.services.research_schema import ensure_research_schema\nensure_research_schema(engine,Base.metadata)\nmodule='paper_monitor.research_smoke'")
    c['command']=['python','-c',script]
    arn=ecs.register_task_definition(**task)['taskDefinition']['taskDefinitionArn']
    run=ecs.run_task(cluster=CLUSTER,taskDefinition=arn,launchType='FARGATE',networkConfiguration=svc['networkConfiguration'],overrides={'containerOverrides':[{'name':c['name'],'command':['python','-c',script,'--check']}]})
    assert not run.get('failures')
    release={'previous':svc['taskDefinition'],'task_definition':arn,'canary':run['tasks'][0]['taskArn'],'sha256':sha,'files':{p:hashlib.sha256(v.encode()).hexdigest() for p,v in files.items()}}
    record.write_text(json.dumps(release,indent=2));print(json.dumps(release))


if __name__=='__main__':main()
