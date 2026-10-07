"""Run a labelled private delivery acceptance in the deployed ECS monitor runtime."""
import argparse
import json
from pathlib import Path
import uuid

import boto3
from aws import BOOTSTRAP


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', default='pas-sdl0-dev')
    ap.add_argument('--region', default='ca-central-1')
    ap.add_argument('--weekly', action='store_true', help='Test labelled recap parent and thread using an isolated sample')
    ap.add_argument('--subscribers', action='store_true', help='Test two isolated subscriber receipts; both test messages go only to the operator')
    args = ap.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ecs = session.client('ecs')
    cluster = 'paper-attribution-dev-cluster'
    service = ecs.describe_services(cluster=cluster, services=['paper-attribution-dev-backend-svc'])['services'][0]
    stack = session.client('cloudformation').describe_stacks(StackName='paper-attribution-dev-author-monitor')['Stacks'][0]
    definition = next(o['OutputValue'] for o in stack['Outputs'] if o['OutputKey'] == 'TaskArn')
    test_id = str(uuid.uuid4())
    if args.weekly and args.subscribers:
        ap.error('Choose either --weekly or --subscribers')
    worker = Path(__file__).with_name('subscribers_probe.py' if args.subscribers else 'freshness_probe.py').read_text()
    command = BOOTSTRAP[:BOOTSTRAP.index('os.execv(')] + f'os.execv(sys.executable,[sys.executable,"-c",{worker!r}])'
    overrides = {'containerOverrides': [{'name': 'monitor', 'command': ['python', '-c', command],
        'environment': [{'name': 'FRESHNESS_TEST_ID', 'value': test_id},
                        {'name': 'FRESHNESS_TEST_MODE', 'value': 'weekly' if args.weekly else 'immediate'}]}]}
    assert len(json.dumps(overrides)) < 8192
    record = {'test_id': test_id, 'status': 'dispatching', 'task_definition': definition}
    path = Path(__file__).parent / 'build' / ('freshness-probe-' + test_id + '.json')
    path.write_text(json.dumps(record, indent=2))
    result = ecs.run_task(cluster=cluster, taskDefinition=definition, launchType='FARGATE',
        networkConfiguration=service['networkConfiguration'], overrides=overrides, clientToken=test_id)
    if result.get('failures'):
        raise RuntimeError(result['failures'])
    record.update(status='dispatched', task_arn=result['tasks'][0]['taskArn'])
    path.write_text(json.dumps(record, indent=2))
    print(json.dumps(record))


if __name__ == '__main__':
    main()
