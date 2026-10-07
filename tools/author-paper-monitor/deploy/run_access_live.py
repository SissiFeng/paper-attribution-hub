import base64,json
import boto3
from reading_aws import BUILD,ROOT,CLUSTER
s=boto3.Session(profile_name='pas-sdl0-dev',region_name='ca-central-1');e=s.client('ecs')
r=json.loads((BUILD/'p0-backend-release.json').read_text());t=e.describe_task_definition(taskDefinition=r['task_definition'])['taskDefinition'];c=t['containerDefinitions'][0]
script=c['command'][2].split("module='paper_monitor.access_smoke'")[0]
source=base64.b64encode((ROOT/'deploy/access_live_probe.py').read_bytes()).decode()
script+="\nimport base64\nexec(compile(base64.b64decode('"+source+"'),'<access-live-probe>','exec'))\n"
before=json.loads((BUILD/'p0-backend-before.json').read_text())
result=e.run_task(cluster=CLUSTER,taskDefinition=r['task_definition'],launchType='FARGATE',networkConfiguration=before['service']['networkConfiguration'],overrides={'containerOverrides':[{'name':c['name'],'command':['python','-c',script]}]})
assert not result.get('failures');record={'task':result['tasks'][0]['taskArn'],'definition':r['task_definition']};(BUILD/'p0-live-task.json').write_text(json.dumps(record));print(json.dumps(record))
