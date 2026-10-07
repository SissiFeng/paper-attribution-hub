import base64,json
import boto3
from reading_aws import BUILD,ROOT,CLUSTER,SERVICE
s=boto3.Session(profile_name='pas-sdl0-dev',region_name='ca-central-1');e=s.client('ecs')
r=json.loads((BUILD/'p1-release.json').read_text());svc=e.describe_services(cluster=CLUSTER,services=[SERVICE])['services'][0]
assert svc['taskDefinition']==r['task_definition']
t=e.describe_task_definition(taskDefinition=r['task_definition'])['taskDefinition'];c=t['containerDefinitions'][0]
script=c['command'][2].split("module='paper_monitor.research_smoke'")[0]
source=base64.b64encode((ROOT/'deploy/research_live_probe.py').read_bytes()).decode()
script+="\nimport base64\nexec(compile(base64.b64decode('"+source+"'),'<research-live-probe>','exec'))\n"
result=e.run_task(cluster=CLUSTER,taskDefinition=r['task_definition'],launchType='FARGATE',networkConfiguration=svc['networkConfiguration'],overrides={'containerOverrides':[{'name':c['name'],'command':['python','-c',script]}]})
assert not result.get('failures');record={'task':result['tasks'][0]['taskArn'],'definition':r['task_definition']};(BUILD/'p1-live-task.json').write_text(json.dumps(record));print(json.dumps(record))
