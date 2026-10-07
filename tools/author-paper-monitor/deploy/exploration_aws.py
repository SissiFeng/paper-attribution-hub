"""P2 overlay on the currently deployed immutable P1 release; canary before promotion."""
import argparse
import copy
import hashlib
import io
import json
import zipfile
from reading_aws import BUILD, REPO, ROOT, BUCKET, CLUSTER, SERVICE, once, aws_session

FILES = ('api/exploration.py', 'models/exploration.py', 'services/research_exploration.py',
    'services/exploration_schema.py', 'services/exploration_worker.py', 'services/access_control.py')


def bundle():
    with zipfile.ZipFile(BUILD/'p2-before.zip') as archive:
        files={n:archive.read(n).decode() for n in archive.namelist()}
    files.update({'app/'+p:(REPO/'backend/app'/p).read_text() for p in FILES})
    files['app/main.py']=once(files['app/main.py'], 'app.include_router(research.router)',
        'app.include_router(research.router)\nfrom app.api import exploration\napp.include_router(exploration.router)\nfrom app.services.exploration_worker import install_worker\ninstall_worker(app)')
    files['app/models/__init__.py']=once(files['app/models/__init__.py'], 'all_models = (',
        'from app.models.exploration import ResearchConnection, ResearchWatch, ResearchScreening, ResearchAlert, ResearchAlertReceipt\n\nall_models = (\n    ResearchConnection, ResearchWatch, ResearchScreening, ResearchAlert, ResearchAlertReceipt,')
    files['paper_monitor/exploration_smoke.py']=(ROOT/'paper_monitor/exploration_smoke.py').read_text()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        for path,source in sorted(files.items()):
            compile(source,path,'exec');archive.writestr(zipfile.ZipInfo(path,date_time=(2026,1,1,0,0,0)),source)
    return output.getvalue()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--promote',action='store_true');args=parser.parse_args()
    aws=aws_session();ecs=aws.client('ecs');s3=aws.client('s3')
    svc=ecs.describe_services(cluster=CLUSTER,services=[SERVICE])['services'][0]
    snapshot=BUILD/'p2-before.json';record=BUILD/'p2-release.json'
    if not snapshot.exists():
        current=ecs.describe_task_definition(taskDefinition=svc['taskDefinition'])['taskDefinition']
        env={e['name']:e['value'] for e in current['containerDefinitions'][0]['environment']}
        raw=s3.get_object(Bucket=env['P0_BUCKET'],Key=env['P0_KEY'])['Body'].read()
        assert hashlib.sha256(raw).hexdigest()==env['P0_SHA256']
        (BUILD/'p2-before.zip').write_bytes(raw)
        snapshot.touch(mode=0o600);snapshot.write_text(json.dumps({'service':svc,'task':current},default=str))
    before=json.loads(snapshot.read_text());raw=bundle();sha=hashlib.sha256(raw).hexdigest()
    assert svc['taskDefinition']==before['task']['taskDefinitionArn'], 'Live service changed; reconcile release before deploying.'
    if args.promote:
        release=json.loads(record.read_text());assert release['sha256']==sha
        canary=ecs.describe_tasks(cluster=CLUSTER,tasks=[release['canary']])['tasks'][0]
        assert canary['taskDefinitionArn']==release['task_definition'] and canary['lastStatus']=='STOPPED' and canary['containers'][0].get('exitCode')==0
        ecs.update_service(cluster=CLUSTER,service=SERVICE,taskDefinition=release['task_definition'])
        print(json.dumps({'promoted':release['task_definition'],'sha256':sha}));return
    print(json.dumps({'sha256':sha,'updated_files':FILES}))
    if not args.apply:return
    if record.exists():
        previous=json.loads(record.read_text());task=ecs.describe_tasks(cluster=CLUSTER,tasks=[previous['canary']])['tasks'][0]
        assert task['lastStatus']=='STOPPED', 'Previous canary is still running.'
        (BUILD/('p2-canary-'+previous['canary'].rsplit('/',1)[-1]+'.json')).write_text(json.dumps(previous,indent=2))
    key='author-monitor/access/releases/p2-'+sha+'.zip'
    s3.put_object(Bucket=BUCKET,Key=key,Body=raw,ServerSideEncryption='AES256')
    allowed=ecs.meta.service_model.operation_model('RegisterTaskDefinition').input_shape.members
    task={k:copy.deepcopy(v) for k,v in before['task'].items() if k in allowed};c=task['containerDefinitions'][0]
    env={e['name']:e['value'] for e in c['environment']};env.update(P0_BUCKET=BUCKET,P0_KEY=key,P0_SHA256=sha,PAS_EXPLORATION_WORKER='1')
    c['environment']=[{'name':k,'value':v} for k,v in env.items()]
    script=once(c['command'][2],"module='paper_monitor.research_smoke'", "from app.services.exploration_schema import ensure_exploration_schema\nensure_exploration_schema(engine,Base.metadata)\nmodule='paper_monitor.exploration_smoke'")
    c['command']=['python','-c',script]
    arn=ecs.register_task_definition(**task)['taskDefinition']['taskDefinitionArn']
    run=ecs.run_task(cluster=CLUSTER,taskDefinition=arn,launchType='FARGATE',networkConfiguration=svc['networkConfiguration'],
        overrides={'containerOverrides':[{'name':c['name'],'command':['python','-c',script,'--check'],'environment':[{'name':'PAS_EXPLORATION_WORKER','value':'0'}]}]})
    assert not run.get('failures')
    release={'previous':svc['taskDefinition'],'task_definition':arn,'canary':run['tasks'][0]['taskArn'],'sha256':sha}
    record.write_text(json.dumps(release,indent=2));print(json.dumps(release))


if __name__=='__main__':main()
