"""Run the bounded P2 HTTPS probe after the release is stable."""
import base64
import json
import zlib
from reading_aws import BUILD, ROOT, CLUSTER, SERVICE, aws_session

s=aws_session(); e=s.client('ecs')
r=json.loads((BUILD/'p2-release.json').read_text())
record_path=BUILD/'p2-live-task.json'
if record_path.exists():
    previous=e.describe_tasks(cluster=CLUSTER,tasks=[json.loads(record_path.read_text())['task']])['tasks']
    assert not previous or previous[0]['lastStatus']=='STOPPED', 'The previous P2 live probe is still running.'
svc=e.describe_services(cluster=CLUSTER,services=[SERVICE])['services'][0]
assert svc['taskDefinition']==r['task_definition']
assert len(svc['deployments'])==1 and svc['deployments'][0]['rolloutState']=='COMPLETED'
t=e.describe_task_definition(taskDefinition=r['task_definition'])['taskDefinition']; c=t['containerDefinitions'][0]
script=c['command'][2].split("module='paper_monitor.exploration_smoke'")[0]
source=base64.b64encode(zlib.compress((ROOT/'deploy/exploration_live_probe.py').read_bytes())).decode()
script+="\nimport base64,zlib\nexec(compile(zlib.decompress(base64.b64decode('"+source+"')),'<exploration-live-probe>','exec'))\n"
result=e.run_task(cluster=CLUSTER,taskDefinition=r['task_definition'],launchType='FARGATE',
    networkConfiguration=svc['networkConfiguration'],overrides={'containerOverrides':[{'name':c['name'],
    'command':['python','-c',script],'environment':[{'name':'PAS_EXPLORATION_WORKER','value':'0'}]}]})
assert not result.get('failures')
record={'task':result['tasks'][0]['taskArn'],'definition':r['task_definition']}
record_path.write_text(json.dumps(record));print(json.dumps(record))
