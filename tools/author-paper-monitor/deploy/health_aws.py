"""Deploy an independent 15-minute watchdog and AWS-event -> private Slack alerts."""

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


def template(args, account, key, alarms):
    function = args.stack + "-watchdog"
    function_arn = {"Fn::GetAtt": ["Watchdog", "Arn"]}
    env = {
        "SLACK_TABLE": args.slack_stack,
        "SLACK_CONFIG_PARAMETER": "/" + args.slack_stack + "/credentials",
        "MONITOR_ALARMS": json.dumps(alarms),
        "MONITOR_COLLECTOR_ALARM_PREFIX": args.monitor_stack + '-',
    }
    resources = {
        "Role": {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "AssumeRolePolicyDocument": role("lambda.amazonaws.com"),
                "ManagedPolicyArns": [
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                ],
                "Policies": [
                    {
                        "PolicyName": "PrivateMonitorAlerts",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                policy(
                                    ["dynamodb:GetItem", "dynamodb:PutItem"],
                                    f"arn:aws:dynamodb:{args.region}:{account}:table/{args.slack_stack}",
                                ),
                                policy(
                                    "ssm:GetParameter",
                                    f"arn:aws:ssm:{args.region}:{account}:parameter/{args.slack_stack}/credentials",
                                ),
                                policy("cloudwatch:DescribeAlarms", "*"),
                            ],
                        },
                    }
                ],
            },
        },
        "Logs": {
            "Type": "AWS::Logs::LogGroup",
            "Properties": {
                "LogGroupName": "/aws/lambda/" + function,
                "RetentionInDays": 30,
            },
        },
        "Watchdog": {
            "Type": "AWS::Lambda::Function",
            "DependsOn": "Logs",
            "Properties": {
                "FunctionName": function,
                "Runtime": "python3.12",
                "Handler": "paper_monitor.health.handler",
                "Role": {"Fn::GetAtt": ["Role", "Arn"]},
                "Timeout": 60,
                "MemorySize": 256,
                "Code": {"S3Bucket": args.bucket, "S3Key": key},
                "Environment": {"Variables": env},
            },
        },
        "Schedule": {
            "Type": "AWS::Events::Rule",
            "Properties": {
                "Name": args.stack + "-watchdog",
                "ScheduleExpression": "rate(15 minutes)",
                "State": "ENABLED",
                "Targets": [{"Id": "watchdog", "Arn": function_arn}],
            },
        },
        "TaskFailures": {
            "Type": "AWS::Events::Rule",
            "Properties": {
                "EventPattern": {
                    "source": ["aws.ecs"],
                    "detail-type": ["ECS Task State Change"],
                    "detail": {
                        "taskDefinitionArn": [
                            {
                                "prefix": f"arn:aws:ecs:{args.region}:{account}:task-definition/{args.monitor_stack}:"
                            }
                        ],
                        "lastStatus": ["STOPPED"],
                        "$or": [
                            {"stopCode": ["TaskFailedToStart"]},
                            {"containers": {"exitCode": [{"anything-but": 0}]}},
                        ],
                    },
                },
                "Targets": [{"Id": "watchdog", "Arn": function_arn}],
            },
        },
        "AlarmEvents": {
            "Type": "AWS::Events::Rule",
            "Properties": {
                "EventPattern": {
                    "source": ["aws.cloudwatch"],
                    "detail-type": ["CloudWatch Alarm State Change"],
                    "detail": {"alarmName": alarms, "state": {"value": ["ALARM"]}},
                },
                "Targets": [{"Id": "watchdog", "Arn": function_arn},
                            {"Id": "independent-alert", "Arn": {"Ref": "Alerts"}}],
            },
        },
        "WatchdogAlarm": {
            "Type": "AWS::CloudWatch::Alarm",
            "Properties": {
                "AlarmDescription": "Watchdog cannot deliver private alerts; inspect its durable receipt",
                "Namespace": "AWS/Lambda",
                "MetricName": "Errors",
                "Dimensions": [{"Name": "FunctionName", "Value": function}],
                "Statistic": "Sum",
                "Period": 300,
                "EvaluationPeriods": 1,
                "Threshold": 0,
                "ComparisonOperator": "GreaterThanThreshold",
                "TreatMissingData": "notBreaching",
                "AlarmActions": [{"Ref": "Alerts"}],
            },
        },
        'Alerts': {'Type': 'AWS::SNS::Topic', 'Properties': {
            'TopicName': args.stack + '-alerts'}},
        'AlertPolicy': {'Type': 'AWS::SNS::TopicPolicy', 'Properties': {
            'Topics': [{'Ref': 'Alerts'}], 'PolicyDocument': {'Version': '2012-10-17',
                'Statement': [
                    {'Effect': 'Allow', 'Principal': {'Service': 'events.amazonaws.com'},
                     'Action': 'sns:Publish', 'Resource': {'Ref': 'Alerts'},
                     'Condition': {'ArnEquals': {'aws:SourceArn': {'Fn::GetAtt': ['AlarmEvents', 'Arn']}}}},
                    {'Effect': 'Allow', 'Principal': {'Service': 'cloudwatch.amazonaws.com'},
                     'Action': 'sns:Publish', 'Resource': {'Ref': 'Alerts'},
                     'Condition': {'StringEquals': {'aws:SourceAccount': account}}}
                ]}}},
        'EmailAlerts': {'Type': 'AWS::SNS::Subscription', 'Condition': 'HasAlertEmail',
            'Properties': {'TopicArn': {'Ref': 'Alerts'}, 'Protocol': 'email', 'Endpoint': {'Ref': 'AlertEmail'}}},
    }
    for name in ("Schedule", "TaskFailures", "AlarmEvents"):
        resources[name + "Permission"] = {
            "Type": "AWS::Lambda::Permission",
            "Properties": {
                "FunctionName": {"Ref": "Watchdog"},
                "Action": "lambda:InvokeFunction",
                "Principal": "events.amazonaws.com",
                "SourceArn": {"Fn::GetAtt": [name, "Arn"]},
            },
        }
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        'Parameters': {'AlertEmail': {'Type': 'String', 'Default': '',
            'Description': 'Operator email; SNS requires the recipient to confirm its subscription'}},
        'Conditions': {'HasAlertEmail': {'Fn::Not': [{'Fn::Equals': [{'Ref': 'AlertEmail'}, '']}]}},
        "Resources": resources,
        "Outputs": {"Watchdog": {"Value": {"Ref": "Watchdog"}},
                    'AlertTopic': {'Value': {'Ref': 'Alerts'}}},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="pas-sdl0-dev")
    parser.add_argument("--region", default="ca-central-1")
    parser.add_argument("--stack", default="paper-attribution-dev-monitor-health")
    parser.add_argument(
        "--monitor-stack", default="paper-attribution-dev-author-monitor"
    )
    parser.add_argument("--slack-stack", default="paper-attribution-dev-slack")
    parser.add_argument(
        "--bucket", default="paper-attribution-artifacts-dev-247893369214"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument('--alert-email', help='Authorized operator email for independent AWS alerts; omit to preserve the existing subscription')
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    cfn = session.client("cloudformation")
    alarms = []
    for stack in (args.monitor_stack, args.slack_stack):
        alarms.extend(
            r["PhysicalResourceId"]
            for r in cfn.list_stack_resources(StackName=stack)["StackResourceSummaries"]
            if r["ResourceType"] == "AWS::CloudWatch::Alarm"
        )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted((ROOT / "paper_monitor").glob("*.py")):
            z.writestr(
                zipfile.ZipInfo(
                    str(p.relative_to(ROOT)), date_time=(2026, 1, 1, 0, 0, 0)
                ),
                p.read_bytes(),
            )
    data = archive.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    key = "author-monitor/health-releases/" + digest + ".zip"
    doc = template(args, account, key, alarms)
    body = json.dumps(doc, indent=2)
    build = ROOT / "deploy/build"
    build.mkdir(exist_ok=True)
    (build / "health-stack.json").write_text(body)
    cfn.validate_template(TemplateBody=body)
    print(
        json.dumps(
            {
                "template": str(build / "health-stack.json"),
                "sha256": digest,
                "watched_alarms": len(alarms),
            }
        )
    )
    if not args.apply:
        return
    session.client("s3").put_object(
        Bucket=args.bucket, Key=key, Body=data, ServerSideEncryption="AES256"
    )
    try:
        previous_stack = cfn.describe_stacks(StackName=args.stack)['Stacks'][0]
    except ClientError as exc:
        if "does not exist" not in str(exc):
            raise
        cfn.create_stack(
            StackName=args.stack, TemplateBody=body, Capabilities=["CAPABILITY_IAM"]
            , Parameters=[{'ParameterKey': 'AlertEmail', 'ParameterValue': args.alert_email or ''}]
        )
        waiter = "stack_create_complete"
    else:
        try:
            cfn.update_stack(
                StackName=args.stack, TemplateBody=body, Capabilities=["CAPABILITY_IAM"]
                , Parameters=[{'ParameterKey': 'AlertEmail', **(
                    {'UsePreviousValue': True} if args.alert_email is None and any(
                        p['ParameterKey'] == 'AlertEmail' for p in previous_stack.get('Parameters', []))
                    else {'ParameterValue': args.alert_email or ''})}]
            )
            waiter = "stack_update_complete"
        except ClientError as exc:
            if "No updates" not in str(exc):
                raise
            waiter = None
    if waiter:
        cfn.get_waiter(waiter).wait(
            StackName=args.stack, WaiterConfig={"Delay": 10, "MaxAttempts": 90}
        )
    outputs = {
        o["OutputKey"]: o["OutputValue"]
        for o in cfn.describe_stacks(StackName=args.stack)["Stacks"][0]["Outputs"]
    }
    (build / "health-deployment.json").write_text(
        json.dumps({"sha256": digest, **outputs}, indent=2)
    )
    print(json.dumps(outputs))


if __name__ == "__main__":
    main()
