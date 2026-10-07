"""Scoped reading release over the current immutable backend and its Jev overlay."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile
import subprocess
import boto3
from botocore.exceptions import TokenRetrievalError, UnauthorizedSSOTokenError

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1];BUILD=ROOT/'deploy/build'
BUCKET='paper-attribution-artifacts-dev-247893369214';CLUSTER='paper-attribution-dev-cluster';SERVICE='paper-attribution-dev-backend-svc'
PUBLIC='https://d1ai8ldqsh81fz.cloudfront.net'
NEW=('api/chat.py','api/reader_auth.py','api/reading.py','models/chat.py','models/reading.py',
     'services/chat_service.py','services/grounded_answer_service.py','services/chat_access.py',
     'services/reader_auth.py','services/reading_schema.py')

def aws_session():
    session=boto3.Session(profile_name='pas-sdl0-dev',region_name='ca-central-1')
    try:
        session.get_credentials().get_frozen_credentials()
        return session
    except (TokenRetrievalError, UnauthorizedSSOTokenError):
        # The CLI may still have valid role credentials when the SDK cannot
        # refresh its SSO token. Reuse that same profile, in memory only.
        credentials=json.loads(subprocess.check_output([
            'aws','configure','export-credentials','--profile','pas-sdl0-dev','--format','process'],text=True))
        return boto3.Session(region_name='ca-central-1',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'])

def once(value,old,new):
    if value.count(old)!=1: raise ValueError('Deployed patch anchor drift: '+old[:60])
    return value.replace(old,new,1)

def bundle():
    base=json.loads((BUILD/'reading-base.json').read_text())['files']
    files={'app/'+p:(REPO/'backend/app'/p).read_text() for p in NEW}
    middleware='''
from app.api import chat, reader_auth, reading
app.include_router(chat.router)
app.include_router(reader_auth.router)
app.include_router(reading.router)

@app.middleware("http")
async def private_response_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/auth/", "/chat/", "/reading/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response

'''
    files['app/main.py']=once(base['app/main.py'],'app.include_router(papers.router)',middleware+'app.include_router(papers.router)')
    imports='from app.models.chat import ChatSession, ChatMessage\nfrom app.models.reading import Reader, ReaderSession, Bookmark, ChatParticipant\n\n'
    files['app/models/__init__.py']=once(base['app/models/__init__.py'],'all_models = (',imports+'all_models = (\n    ChatSession, ChatMessage, Reader, ReaderSession, Bookmark, ChatParticipant,')
    files['paper_monitor/reading_smoke.py']=(ROOT/'paper_monitor/reading_smoke.py').read_text()
    for path,content in files.items():compile(content,path,'exec')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for path,content in sorted(files.items()):z.writestr(zipfile.ZipInfo(path,date_time=(2026,1,1,0,0,0)),content)
    return out.getvalue(),files


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');ap.add_argument('--promote',action='store_true');args=ap.parse_args()
    data,files=bundle();sha=hashlib.sha256(data).hexdigest();key=f'author-monitor/reading/releases/{sha}.zip'
    s=boto3.Session(profile_name='pas-sdl0-dev',region_name='ca-central-1');ecs=s.client('ecs')
    svc=ecs.describe_services(cluster=CLUSTER,services=[SERVICE])['services'][0]
    if args.promote:
        release=json.loads((BUILD/'reading-release.json').read_text());assert release['sha256']==sha
        task=ecs.describe_tasks(cluster=CLUSTER,tasks=[release['canary']])['tasks'][0]
        assert task['lastStatus']=='STOPPED' and task['containers'][0].get('exitCode')==0
        assert task['taskDefinitionArn']==release['task_definition'];assert svc['taskDefinition']==release['previous']
        ecs.update_service(cluster=CLUSTER,service=SERVICE,taskDefinition=release['task_definition']);print(json.dumps(release));return
    print(json.dumps({'sha256':sha,'files':list(files)}))
    if not args.apply:return
    origin=json.loads((BUILD/'reading-base-origin.json').read_text());assert svc['taskDefinition']==origin['base_task']
    current=ecs.describe_task_definition(taskDefinition=svc['taskDefinition'])['taskDefinition'];assert current['containerDefinitions'][0]['image']==origin['image']
    s.client('s3').put_object(Bucket=BUCKET,Key=key,Body=data,ServerSideEncryption='AES256')
    s.client('iam').put_role_policy(RoleName=current['taskRoleArn'].rsplit('/',1)[-1],PolicyName='PrivateReading',PolicyDocument=json.dumps({'Version':'2012-10-17','Statement':[
        {'Effect':'Allow','Action':'s3:GetObject','Resource':f'arn:aws:s3:::{BUCKET}/author-monitor/reading/releases/*'},
        {'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:PutItem','dynamodb:UpdateItem'],'Resource':'arn:aws:dynamodb:ca-central-1:247893369214:table/paper-attribution-dev-slack'}]}))
    allowed=ecs.meta.service_model.operation_model('RegisterTaskDefinition').input_shape.members
    revised={k:copy.deepcopy(v) for k,v in current.items() if k in allowed};c=revised['containerDefinitions'][0]
    env={e['name']:e['value'] for e in c['environment']};env.update(PAS_PUBLIC_URL=PUBLIC,PAS_SLACK_TEAM_ID='T012M3T3U01',PAS_SLACK_APP_ID='A0C6VPXEQ5C',PAS_SLACK_TABLE='paper-attribution-dev-slack',PAS_CHAT_WIKI_PLANNING='0',READING_BUCKET=BUCKET,READING_KEY=key,READING_SHA256=sha)
    c['environment']=[{'name':k,'value':v} for k,v in env.items()]
    bootstrap=c['command'][2].split("module='paper_monitor.jev_backend_smoke'")[0]+'''
raw=boto3.client('s3').get_object(Bucket=os.environ['READING_BUCKET'],Key=os.environ['READING_KEY'])['Body'].read()
if hashlib.sha256(raw).hexdigest()!=os.environ['READING_SHA256']: raise RuntimeError('Reading overlay checksum mismatch')
zipfile.ZipFile(io.BytesIO(raw)).extractall('/app')
from app.db import Base,engine
from app.models import all_models
from app.services.reading_schema import ensure_reading_schema
ensure_reading_schema(engine,Base.metadata)
module='paper_monitor.reading_smoke' if '--check' in sys.argv else 'app.scripts.serve'
os.execv(sys.executable,[sys.executable,'-m',module])'''
    c['command']=['python','-c',bootstrap]
    arn=ecs.register_task_definition(**revised)['taskDefinition']['taskDefinitionArn']
    run=ecs.run_task(cluster=CLUSTER,taskDefinition=arn,launchType='FARGATE',networkConfiguration=svc['networkConfiguration'],overrides={'containerOverrides':[{'name':c['name'],'command':['python','-c',bootstrap,'--check']}]});assert not run.get('failures')
    release={'previous':svc['taskDefinition'],'task_definition':arn,'canary':run['tasks'][0]['taskArn'],'sha256':sha,'files':{p:hashlib.sha256(v.encode()).hexdigest() for p,v in files.items()}}
    (BUILD/'reading-release.json').write_text(json.dumps(release,indent=2));print(json.dumps(release))

if __name__=='__main__':main()
