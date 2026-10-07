"""Enable PAS evidence-based generation with a hidden key or existing SSM secret.

This changes only provider configuration on the current backend task. It never
prints credentials. Provider API usage is billed by the selected provider.
"""
import argparse
import copy
import getpass
import json
import boto3


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--provider',choices=['anthropic','kimi'],required=True)
    ap.add_argument('--parameter',help='Existing SecureString SSM parameter containing only the provider API key')
    ap.add_argument('--profile',default='pas-sdl0-dev');ap.add_argument('--region',default='ca-central-1')
    args=ap.parse_args()
    s=boto3.Session(profile_name=args.profile,region_name=args.region);ssm=s.client('ssm');ecs=s.client('ecs')
    account=s.client('sts').get_caller_identity()['Account']
    param=args.parameter or '/paper-attribution-dev/reading/'+args.provider+'-api-key'
    if not param.startswith('/'):
        raise ValueError('Use an absolute SSM parameter name beginning with /.')
    if args.parameter:
        metadata=ssm.get_parameter(Name=param)['Parameter']
        if metadata['Type']!='SecureString':raise ValueError('Use an encrypted SecureString parameter.')
    else:
        key=getpass.getpass(args.provider+' API key (hidden): ').strip()
        if not key:raise ValueError('Empty key; no configuration changed.')
        ssm.put_parameter(Name=param,Type='SecureString',Value=key,Overwrite=True)
    cluster='paper-attribution-dev-cluster';service='paper-attribution-dev-backend-svc'
    svc=ecs.describe_services(cluster=cluster,services=[service])['services'][0]
    task=ecs.describe_task_definition(taskDefinition=svc['taskDefinition'])['taskDefinition']
    allowed=ecs.meta.service_model.operation_model('RegisterTaskDefinition').input_shape.members
    revised={k:copy.deepcopy(v) for k,v in task.items() if k in allowed};container=revised['containerDefinitions'][0]
    variable='PAS_'+args.provider.upper()+'_API_KEY'
    arn=f'arn:aws:ssm:{args.region}:{account}:parameter{param}'
    s.client('iam').put_role_policy(RoleName=task['executionRoleArn'].rsplit('/',1)[-1],PolicyName='ReadingModelCredential',PolicyDocument=json.dumps({'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':'ssm:GetParameters','Resource':arn}]}))
    container['secrets']=[v for v in container.get('secrets',[]) if v['name'] not in ('PAS_KIMI_API_KEY','PAS_ANTHROPIC_API_KEY')]+[{'name':variable,'valueFrom':arn}]
    container['environment']=[v for v in container.get('environment',[]) if v['name'] not in ('PAS_KIMI_API_KEY','PAS_ANTHROPIC_API_KEY','PAS_LLM_PROVIDER')]+[{'name':'PAS_LLM_PROVIDER','value':args.provider}]
    new=ecs.register_task_definition(**revised)['taskDefinition']['taskDefinitionArn']
    ecs.update_service(cluster=cluster,service=service,taskDefinition=new)
    print(json.dumps({'provider':args.provider,'credential_parameter':param,'previous_task':task['taskDefinitionArn'],'new_task':new,'deployment_requested':True,'next':'Wait for service stability and test a cited answer in PAS.'}))


if __name__=='__main__':main()
