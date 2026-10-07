"""Deploy an isolated scheduled ECS monitor alongside the existing PAS service.

Uses the running backend image by immutable digest; the reviewed monitor bundle is
content-addressed in S3. Does not rebuild or deploy unrelated local backend edits.
Run with the backend virtualenv. Credentials come from the selected AWS profile.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = '''import boto3,hashlib,io,os,sys,zipfile
b=boto3.client("s3").get_object(Bucket=os.environ["MONITOR_BUCKET"],Key=os.environ["MONITOR_BUNDLE"])['Body'].read()
if hashlib.sha256(b).hexdigest()!=os.environ["MONITOR_SHA256"]: raise RuntimeError("Bundle checksum mismatch")
zipfile.ZipFile(io.BytesIO(b)).extractall("/opt/author-monitor")
os.environ["PYTHONPATH"]="/opt/author-monitor:/app"
os.execv(sys.executable,[sys.executable,"-m","paper_monitor.aws_runner",*sys.argv[1:]])'''


def role(service):
    return {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}]}


def policy(actions, resource):
    return {"Effect": "Allow", "Action": actions, "Resource": resource}


def template(args, account, task, network, digest, bundle_key, bundle_hash, db_parameter):
    prefix = args.stack
    bucket_arn = f"arn:aws:s3:::{args.bucket}"
    parameter_arns = [f"arn:aws:ssm:{args.region}:{account}:parameter{db_parameter}"]
    secrets = [{"Name": "PAS_DATABASE_URL", "ValueFrom": parameter_arns[0]}]
    if args.slack_parameter:
        arn = f"arn:aws:ssm:{args.region}:{account}:parameter{args.slack_parameter}"
        parameter_arns.append(arn)
        secrets.append({"Name": "SLACK_WEBHOOK_URL", "ValueFrom": arn})
    old = task["containerDefinitions"][0]
    for secret in old.get("secrets", []):
        if secret["name"] == "PAS_OPENALEX_MAILTO":
            secrets.append({"Name": "CONTACT_EMAIL", "ValueFrom": secret["valueFrom"]})
            parameter_arns.append(secret["valueFrom"])
    if args.slack_app:
        parameter_arns.append(f"arn:aws:ssm:{args.region}:{account}:parameter/{args.slack_app}/credentials")
    env = {"PAS_PUBLIC_URL": getattr(args, 'pas_public_url', 'https://d1ai8ldqsh81fz.cloudfront.net'), "MONITOR_BUCKET": args.bucket, "MONITOR_PREFIX": "author-monitor/production",
           "MONITOR_BUNDLE": bundle_key, "MONITOR_SHA256": bundle_hash,
           "PAS_SDL_STAGE1_ONLY": "false", "PAS_ZOTERO_SOURCE_ONLY": "false",
           "PAS_MONITOR_INGEST": "1", "PAS_MONITOR_MODE": "main",
           "PAS_ACTIVE_LEARNING": "0", "PYTHONUNBUFFERED": "1",
           "SLACK_DELIVERY_MODE": "subscribers", "DEEP_LOOKBACK_DAYS": "365",
           "SCHOLAR_CONFIG_PARAMETER": f"/{args.stack}/scholar-mailbox",
           "OPENALEX_PARAMETER": f"/{args.stack}/openalex-api-key"}
    if args.jev_shadow:
        env.update(JEV_MODE='shadow', JEV_CONFIG_PARAMETER=f'/{args.stack}/jev')
    if args.slack_app:
        env.update(SLACK_TABLE=args.slack_app, SLACK_CONFIG_PARAMETER=f"/{args.slack_app}/credentials")
    resources = {
        "Logs": {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": f"/ecs/{prefix}", "RetentionInDays": 30}},
        "TaskRole": {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": role("ecs-tasks.amazonaws.com"),
            "Policies": [{"PolicyName": "MonitorState", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                policy(["s3:GetObject", "s3:PutObject"], f"{bucket_arn}/author-monitor/*"),
                policy("ssm:GetParameter", f"arn:aws:ssm:{args.region}:{account}:parameter/{args.stack}/openalex-api-key"),
                policy("ssm:GetParameter", f"arn:aws:ssm:{args.region}:{account}:parameter/{args.stack}/scholar-mailbox"),
                {**policy("s3:ListBucket", bucket_arn), "Condition": {"StringLike": {"s3:prefix": "author-monitor/*"}}}
            ]}}]}},
        "ExecutionRole": {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": role("ecs-tasks.amazonaws.com"),
            "ManagedPolicyArns": ["arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"],
            "Policies": [{"PolicyName": "MonitorSecrets", "PolicyDocument": {"Version": "2012-10-17", "Statement": [policy("ssm:GetParameters", parameter_arns)]}}]}},
        "Task": {"Type": "AWS::ECS::TaskDefinition", "Properties": {
            "Family": prefix, "Cpu": "256", "Memory": "512", "NetworkMode": "awsvpc", "RequiresCompatibilities": ["FARGATE"],
            "ExecutionRoleArn": {"Fn::GetAtt": ["ExecutionRole", "Arn"]}, "TaskRoleArn": {"Fn::GetAtt": ["TaskRole", "Arn"]},
            "ContainerDefinitions": [{"Name": "monitor", "Image": digest, "Essential": True,
                "Command": ["python", "-c", BOOTSTRAP], "StopTimeout": 120,
                "Environment": [{"Name": k, "Value": v} for k, v in env.items()], "Secrets": secrets,
                "LogConfiguration": {"LogDriver": "awslogs", "Options": {"awslogs-group": {"Ref": "Logs"}, "awslogs-region": args.region, "awslogs-stream-prefix": "monitor"}}}]}},
        "ScheduleRole": {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": role("events.amazonaws.com"),
            "Policies": [{"PolicyName": "RunMonitor", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                {**policy("ecs:RunTask", {"Ref": "Task"}), "Condition": {"ArnEquals": {"ecs:cluster": f"arn:aws:ecs:{args.region}:{account}:cluster/{args.cluster}"}}},
                policy("iam:PassRole", [{"Fn::GetAtt": ["TaskRole", "Arn"]}, {"Fn::GetAtt": ["ExecutionRole", "Arn"]}])
            ]}}]}},
        "Failures": {"Type": "AWS::SQS::Queue", "Properties": {"MessageRetentionPeriod": 1209600, "SqsManagedSseEnabled": True}},
        "Schedule": {"Type": "AWS::Events::Rule", "Properties": {
            "Name": prefix, "ScheduleExpression": "cron(17 0/4 * * ? *)", "State": "ENABLED" if args.enable_schedule else "DISABLED",
            "Targets": [{"Id": "monitor", "Arn": f"arn:aws:ecs:{args.region}:{account}:cluster/{args.cluster}",
                "RoleArn": {"Fn::GetAtt": ["ScheduleRole", "Arn"]},
                "EcsParameters": {"TaskDefinitionArn": {"Ref": "Task"}, "LaunchType": "FARGATE", "TaskCount": 1,
                    "NetworkConfiguration": {"AwsVpcConfiguration": {"Subnets": network["subnets"], "SecurityGroups": network["securityGroups"], "AssignPublicIp": network["assignPublicIp"]}}},
                "DeadLetterConfig": {"Arn": {"Fn::GetAtt": ["Failures", "Arn"]}},
                "RetryPolicy": {"MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 3600}}]}},
        "FailedTask": {"Type": "AWS::Events::Rule", "Properties": {
            "EventPattern": {"source": ["aws.ecs"], "detail-type": ["ECS Task State Change"], "detail": {
                "clusterArn": [f"arn:aws:ecs:{args.region}:{account}:cluster/{args.cluster}"],
                "taskDefinitionArn": [{"prefix": f"arn:aws:ecs:{args.region}:{account}:task-definition/{prefix}:"}],
                "lastStatus": ["STOPPED"], "stopCode": ["EssentialContainerExited", "TaskFailedToStart"]}},
            "Targets": [{"Id": "failures", "Arn": {"Fn::GetAtt": ["Failures", "Arn"]}}]}},
    }
    if args.slack_app:
        resources["TaskRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"].extend([
            policy(["dynamodb:GetItem", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem"], f"arn:aws:dynamodb:{args.region}:{account}:table/{args.slack_app}"),
            policy("ssm:GetParameter", f"arn:aws:ssm:{args.region}:{account}:parameter/{args.slack_app}/credentials")])
    if args.jev_shadow:
        resources['TaskRole']['Properties']['Policies'][0]['PolicyDocument']['Statement'].append(
            policy('ssm:GetParameter', f'arn:aws:ssm:{args.region}:{account}:parameter/{args.stack}/jev'))
    # Filter non-zero exits separately; task-start failures do not have exitCode.
    resources["FailedTask"]["Properties"]["EventPattern"]["detail"]["$or"] = [
        {"stopCode": ["TaskFailedToStart"]}, {"containers": {"exitCode": [{"anything-but": 0}]}}]
    resources["FailurePolicy"] = {"Type": "AWS::SQS::QueuePolicy", "Properties": {
        "Queues": [{"Ref": "Failures"}], "PolicyDocument": {"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Principal": {"Service": "events.amazonaws.com"}, "Action": "sqs:SendMessage",
            "Resource": {"Fn::GetAtt": ["Failures", "Arn"]},
            "Condition": {"ArnEquals": {"aws:SourceArn": [{"Fn::GetAtt": ["Schedule", "Arn"]}, {"Fn::GetAtt": ["FailedTask", "Arn"]}]}}
        }]}}}
    resources["FailureAlarm"] = {"Type": "AWS::CloudWatch::Alarm", "Properties": {
        "AlarmDescription": "Author monitor failed; inspect the failure queue and ECS logs",
        "Namespace": "AWS/SQS", "MetricName": "ApproximateNumberOfMessagesVisible", "Statistic": "Maximum",
        "Period": 60, "EvaluationPeriods": 1, "Threshold": 0, "ComparisonOperator": "GreaterThanThreshold",
        "TreatMissingData": "notBreaching", "Dimensions": [{"Name": "QueueName", "Value": {"Fn::GetAtt": ["Failures", "QueueName"]}}]}}
    return {"AWSTemplateFormatVersion": "2010-09-09", "Description": "Author paper monitor: persistent state, PAS ingestion and Slack", "Resources": resources,
            "Outputs": {"TaskArn": {"Value": {"Ref": "Task"}}, "FailureQueue": {"Value": {"Ref": "Failures"}}}}


def open_corpus(ecs, args, task):
    wanted = {"PAS_SDL_STAGE1_ONLY": "false", "PAS_ZOTERO_SOURCE_ONLY": "false"}
    current = {e["name"]: e["value"] for e in task["containerDefinitions"][0].get("environment", [])}
    if all(current.get(k) == v for k, v in wanted.items()):
        return task["taskDefinitionArn"]
    allowed = ecs.meta.service_model.operation_model("RegisterTaskDefinition").input_shape.members
    definition = {k: copy.deepcopy(v) for k, v in task.items() if k in allowed}
    env = definition["containerDefinitions"][0]["environment"]
    env[:] = [e for e in env if e["name"] not in wanted]
    env.extend({"name": k, "value": v} for k, v in wanted.items())
    revised = ecs.register_task_definition(**definition)["taskDefinition"]["taskDefinitionArn"]
    ecs.update_service(cluster=args.cluster, service=args.service, taskDefinition=revised)
    print(json.dumps({"backend_previous_task": task["taskDefinitionArn"], "backend_open_corpus_task": revised}))
    return revised


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="pas-sdl0-dev")
    ap.add_argument("--region", default="ca-central-1")
    ap.add_argument("--cluster", default="paper-attribution-dev-cluster")
    ap.add_argument("--service", default="paper-attribution-dev-backend-svc")
    ap.add_argument("--stack", default="paper-attribution-dev-author-monitor")
    ap.add_argument("--bucket", default="paper-attribution-artifacts-dev-247893369214")
    ap.add_argument("--authors", type=Path)
    ap.add_argument("--prefix", default="author-monitor/production")
    ap.add_argument("--slack-parameter")
    ap.add_argument("--slack-app", help="DynamoDB registry / Slack App stack name")
    ap.add_argument('--jev-shadow', action='store_true', help='Enable bounded advisory-only Jev evaluation; credentials are optional')
    ap.add_argument("--enable-schedule", action="store_true")
    ap.add_argument("--open-corpus", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--run", choices=["dry-run", "baseline", "backlog", "verify-ingestion"])
    ap.add_argument('--pas-public-url', default='https://d1ai8ldqsh81fz.cloudfront.net')
    args = ap.parse_args()
    if args.enable_schedule and (not args.authors or (not args.slack_parameter and not args.slack_app) or args.prefix != "author-monitor/production"):
        ap.error("Enabling schedule requires verified production authors and a Slack parameter")
    if args.run in {"dry-run", "verify-ingestion"} and args.prefix == "author-monitor/production":
        ap.error("Use a separate prefix for cloud dry-run")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    ecs, s3, cfn, ssm = [session.client(n) for n in ["ecs", "s3", "cloudformation", "ssm"]]
    service = ecs.describe_services(cluster=args.cluster, services=[args.service])["services"][0]
    task = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    network = service["networkConfiguration"]["awsvpcConfiguration"]
    old = task["containerDefinitions"][0]
    image = old["image"]
    if "@sha256:" not in image:
        repository, tag = image.split("/", 1)[1].rsplit(":", 1)
        digest = session.client("ecr").describe_images(repositoryName=repository, imageIds=[{"imageTag": tag}])["imageDetails"][0]["imageDigest"]
        image = image.rsplit(":", 1)[0] + "@" + digest
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted((ROOT / "paper_monitor").glob("*.py")):
            info = zipfile.ZipInfo(str(path.relative_to(ROOT)), date_time=(2026, 1, 1, 0, 0, 0))
            z.writestr(info, path.read_bytes())
    bundle = archive.getvalue()
    sha = hashlib.sha256(bundle).hexdigest()
    key = f"author-monitor/releases/{sha}.zip"
    db_param = f"/{args.stack}/database-url"
    if args.slack_parameter:
        ssm.get_parameter(Name=args.slack_parameter)  # Validate existence; never print its value.
    if args.authors:
        import sys
        sys.path.insert(0, str(ROOT))
        from paper_monitor.authors import load
        rows = load(args.authors)
        if not rows or any(not a.openalex_ids for a in rows):
            ap.error("Resolve every author before uploading the list")
    doc = template(args, account, task, network, image, key, sha, db_param)
    body = json.dumps(doc, indent=2)
    build = ROOT / "deploy" / "build"
    build.mkdir(exist_ok=True)
    (build / "stack.json").write_text(body)
    cfn.validate_template(TemplateBody=body)
    print(json.dumps({"account": account, "template": str(build / "stack.json"), "image": image, "sha256": sha, "schedule_enabled": args.enable_schedule}))
    if not args.apply:
        return
    db_url = next(e["value"] for e in old["environment"] if e["name"] == "PAS_DATABASE_URL")
    ssm.put_parameter(Name=db_param, Value=db_url, Type="SecureString", Overwrite=True)
    s3.put_object(Bucket=args.bucket, Key=key, Body=bundle, ServerSideEncryption="AES256")
    if args.authors:
        s3.put_object(Bucket=args.bucket, Key=f"{args.prefix}/authors.csv", Body=args.authors.read_bytes(), ServerSideEncryption="AES256")
    try:
        cfn.describe_stacks(StackName=args.stack)
    except ClientError as e:
        if "does not exist" not in str(e):
            raise
        cfn.create_stack(StackName=args.stack, TemplateBody=body, Capabilities=["CAPABILITY_IAM"])
        waiter = "stack_create_complete"
    else:
        try:
            cfn.update_stack(StackName=args.stack, TemplateBody=body, Capabilities=["CAPABILITY_IAM"])
            waiter = "stack_update_complete"
        except ClientError as e:
            if "No updates" not in str(e):
                raise
            waiter = None
    if waiter:
        cfn.get_waiter(waiter).wait(StackName=args.stack, WaiterConfig={"Delay": 10, "MaxAttempts": 90})
    outputs = {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName=args.stack)["Stacks"][0]["Outputs"]}
    if args.open_corpus:
        open_corpus(ecs, args, task)
    if args.run:
        command = ["python", "-c", BOOTSTRAP]
        if args.run == "dry-run":
            command.append("--dry-run")
        elif args.run == "verify-ingestion":
            command.append("--verify-ingestion")
        elif args.run == "backlog":
            command.append("--post-backlog")
        result = ecs.run_task(cluster=args.cluster, taskDefinition=outputs["TaskArn"], launchType="FARGATE", networkConfiguration={"awsvpcConfiguration": network},
            overrides={"containerOverrides": [{"name": "monitor", "command": command, "environment": [{"name": "MONITOR_PREFIX", "value": args.prefix}]}]})
        if result.get("failures"):
            raise RuntimeError(result["failures"])
        outputs["RunTaskArn"] = result["tasks"][0]["taskArn"]
    print(json.dumps(outputs))
    (build / "deployment.json").write_text(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
