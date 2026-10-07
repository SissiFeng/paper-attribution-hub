"""Deploy the small HTTP Slack App alongside the existing ECS collector."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import boto3
from botocore.exceptions import ClientError

from aws import policy, role

ROOT = Path(__file__).resolve().parents[1]


def template(args, account, key):
    param = f'/{args.stack}/credentials'
    env = {'PAS_PUBLIC_URL': getattr(args, 'pas_public_url', 'https://d1ai8ldqsh81fz.cloudfront.net'), 'SLACK_TABLE': {'Ref': 'Data'}, 'SLACK_CONFIG_PARAMETER': param,
           'SLACK_QUEUE': {'Ref': 'Jobs'}, 'MONITOR_BUCKET': args.bucket,
           'OPENALEX_PARAMETER': '/paper-attribution-dev-author-monitor/openalex-api-key',
           'JEV_MODE': 'shadow', 'JEV_CONFIG_PARAMETER': '/paper-attribution-dev-author-monitor/jev',
           'PUBLIC_URL': {'Fn::Sub': 'https://${Api}.execute-api.${AWS::Region}.amazonaws.com'}}
    statements = [policy(['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:Scan'], {'Fn::GetAtt': ['Data', 'Arn']}),
        policy('ssm:GetParameter', [f'arn:aws:ssm:{args.region}:{account}:parameter{param}',
            f'arn:aws:ssm:{args.region}:{account}:parameter/paper-attribution-dev-author-monitor/openalex-api-key',
            f'arn:aws:ssm:{args.region}:{account}:parameter/paper-attribution-dev-author-monitor/jev']),
        policy(['sqs:SendMessage', 'sqs:ReceiveMessage', 'sqs:DeleteMessage', 'sqs:GetQueueAttributes'], {'Fn::GetAtt': ['Jobs', 'Arn']}),
        policy('s3:GetObject', [f'arn:aws:s3:::{args.bucket}/author-monitor/production/state.db',
                             f'arn:aws:s3:::{args.bucket}/author-monitor/production/outbox/jev-shadow.json'])]
    resources = {
        'Data': {'Type': 'AWS::DynamoDB::Table', 'DeletionPolicy': 'Retain', 'UpdateReplacePolicy': 'Retain', 'Properties': {
            'TableName': args.stack, 'BillingMode': 'PAY_PER_REQUEST', 'AttributeDefinitions': [{'AttributeName': 'pk', 'AttributeType': 'S'}],
            'KeySchema': [{'AttributeName': 'pk', 'KeyType': 'HASH'}], 'PointInTimeRecoverySpecification': {'PointInTimeRecoveryEnabled': True},
            'TimeToLiveSpecification': {'AttributeName': 'expires', 'Enabled': True},
            'SSESpecification': {'SSEEnabled': True}}},
        'DeadLetters': {'Type': 'AWS::SQS::Queue', 'Properties': {'MessageRetentionPeriod': 1209600, 'SqsManagedSseEnabled': True}},
        'Jobs': {'Type': 'AWS::SQS::Queue', 'Properties': {'VisibilityTimeout': 540, 'SqsManagedSseEnabled': True,
            'RedrivePolicy': {'deadLetterTargetArn': {'Fn::GetAtt': ['DeadLetters', 'Arn']}, 'maxReceiveCount': 2}}},
        'Role': {'Type': 'AWS::IAM::Role', 'Properties': {'AssumeRolePolicyDocument': role('lambda.amazonaws.com'),
            'ManagedPolicyArns': ['arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'],
            'Policies': [{'PolicyName': 'SlackState', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': statements}}]}},
        'Api': {'Type': 'AWS::ApiGatewayV2::Api', 'Properties': {'Name': args.stack, 'ProtocolType': 'HTTP'}},
        'Integration': {'Type': 'AWS::ApiGatewayV2::Integration', 'Properties': {'ApiId': {'Ref': 'Api'},
            'IntegrationType': 'AWS_PROXY', 'IntegrationUri': {'Fn::GetAtt': ['Ingress', 'Arn']}, 'PayloadFormatVersion': '2.0', 'TimeoutInMillis': 5000}},
        'Route': {'Type': 'AWS::ApiGatewayV2::Route', 'Properties': {'ApiId': {'Ref': 'Api'}, 'RouteKey': '$default',
            'Target': {'Fn::Join': ['/', ['integrations', {'Ref': 'Integration'}]]}}},
        'Stage': {'Type': 'AWS::ApiGatewayV2::Stage', 'Properties': {'ApiId': {'Ref': 'Api'}, 'StageName': '$default', 'AutoDeploy': True,
            'DefaultRouteSettings': {'ThrottlingBurstLimit': 20, 'ThrottlingRateLimit': 10}}},
        'Permission': {'Type': 'AWS::Lambda::Permission', 'Properties': {'Action': 'lambda:InvokeFunction', 'FunctionName': {'Ref': 'Ingress'},
            'Principal': 'apigateway.amazonaws.com', 'SourceArn': {'Fn::Sub': 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${Api}/*'}}},
        'QueueMapping': {'Type': 'AWS::Lambda::EventSourceMapping', 'Properties': {'EventSourceArn': {'Fn::GetAtt': ['Jobs', 'Arn']},
            'FunctionName': {'Ref': 'Worker'}, 'BatchSize': 1, 'Enabled': True}},
        'DeadLettersAlarm': {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {'AlarmDescription': 'Slack jobs need delivery reconciliation',
            'Namespace': 'AWS/SQS', 'MetricName': 'ApproximateNumberOfMessagesVisible', 'Statistic': 'Maximum',
            'Dimensions': [{'Name': 'QueueName', 'Value': {'Fn::GetAtt': ['DeadLetters', 'QueueName']}}],
            'Period': 60, 'EvaluationPeriods': 1, 'Threshold': 0, 'ComparisonOperator': 'GreaterThanThreshold', 'TreatMissingData': 'notBreaching'}},
    }
    for name, handler, timeout in [('Ingress', 'slack_handler', 5), ('Worker', 'slack_worker', 90)]:
        function_name = args.stack + '-' + name.lower()
        resources[name + 'Logs'] = {'Type': 'AWS::Logs::LogGroup', 'Properties': {'LogGroupName': '/aws/lambda/' + function_name, 'RetentionInDays': 30}}
        resources[name] = {'Type': 'AWS::Lambda::Function', 'DependsOn': name + 'Logs', 'Properties': {'FunctionName': function_name,
            'Runtime': 'python3.12', 'Handler': f'paper_monitor.{handler}.handler', 'MemorySize': 1024 if name == 'Ingress' else 512, 'Timeout': timeout,
            'Role': {'Fn::GetAtt': ['Role', 'Arn']}, 'Code': {'S3Bucket': args.bucket, 'S3Key': key}, 'Environment': {'Variables': env}}}
        resources[name + 'Alarm'] = {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {'AlarmDescription': 'AC Papers Slack function errors',
            'Namespace': 'AWS/Lambda', 'MetricName': 'Errors', 'Dimensions': [{'Name': 'FunctionName', 'Value': function_name}],
            'Statistic': 'Sum', 'Period': 300, 'EvaluationPeriods': 1, 'Threshold': 0, 'ComparisonOperator': 'GreaterThanThreshold', 'TreatMissingData': 'notBreaching'}}
    return {'AWSTemplateFormatVersion': '2010-09-09', 'Resources': resources,
        'Outputs': {'Endpoint': {'Value': env['PUBLIC_URL']}, 'Table': {'Value': {'Ref': 'Data'}},
                    'CredentialsParameter': {'Value': param}, 'FailureQueue': {'Value': {'Ref': 'DeadLetters'}}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', default='pas-sdl0-dev')
    ap.add_argument('--region', default='ca-central-1')
    ap.add_argument('--stack', default='paper-attribution-dev-slack')
    ap.add_argument('--bucket', default='paper-attribution-artifacts-dev-247893369214')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--seed-roster', action='store_true')
    ap.add_argument('--pas-public-url', default='https://d1ai8ldqsh81fz.cloudfront.net')
    args = ap.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client('sts').get_caller_identity()['Account']
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted((ROOT / 'paper_monitor').glob('*.py')):
            z.writestr(zipfile.ZipInfo(str(p.relative_to(ROOT)), date_time=(2026, 1, 1, 0, 0, 0)), p.read_bytes())
    data = archive.getvalue()
    key = 'author-monitor/slack-releases/' + hashlib.sha256(data).hexdigest() + '.zip'
    doc = template(args, account, key)
    body = json.dumps(doc, indent=2)
    build = ROOT / 'deploy' / 'build'
    build.mkdir(exist_ok=True)
    (build / 'slack-stack.json').write_text(body)
    cfn = session.client('cloudformation')
    cfn.validate_template(TemplateBody=body)
    if not args.apply:
        print('Validated', build / 'slack-stack.json')
        return
    session.client('s3').put_object(Bucket=args.bucket, Key=key, Body=data, ServerSideEncryption='AES256')
    try:
        cfn.describe_stacks(StackName=args.stack)
    except ClientError as exc:
        if 'does not exist' not in str(exc):
            raise
        cfn.create_stack(StackName=args.stack, TemplateBody=body, Capabilities=['CAPABILITY_IAM'])
        waiter = 'stack_create_complete'
    else:
        try:
            cfn.update_stack(StackName=args.stack, TemplateBody=body, Capabilities=['CAPABILITY_IAM'])
            waiter = 'stack_update_complete'
        except ClientError as exc:
            if 'No updates' not in str(exc):
                raise
            waiter = None
    if waiter:
        cfn.get_waiter(waiter).wait(StackName=args.stack, WaiterConfig={'Delay': 10, 'MaxAttempts': 90})
    outputs = {o['OutputKey']: o['OutputValue'] for o in cfn.describe_stacks(StackName=args.stack)['Stacks'][0]['Outputs']}
    (build / 'slack-deployment.json').write_text(json.dumps(outputs, indent=2))
    import sys
    sys.path.insert(0, str(ROOT))
    from paper_monitor.slack_app import manifest
    (ROOT / 'deploy' / 'slack-manifest.json').write_text(json.dumps(manifest(outputs['Endpoint']), indent=2))
    if args.seed_roster:
        table = session.resource('dynamodb').Table(outputs['Table'])
        count = 0
        for row in json.loads((ROOT / 'config' / 'ac_roster.json').read_text()):
            try:
                table.put_item(Item={'pk': 'author:' + row['person_id'], 'payload': json.dumps(row, ensure_ascii=False), 'version': 1},
                               ConditionExpression='attribute_not_exists(pk)')
                count += 1
            except ClientError as exc:
                if exc.response['Error']['Code'] != 'ConditionalCheckFailedException':
                    raise
        outputs['AuthorsInserted'] = count
    print(json.dumps(outputs))


if __name__ == '__main__':
    main()
