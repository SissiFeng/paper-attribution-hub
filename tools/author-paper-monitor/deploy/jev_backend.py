"""Deploy only reviewed Jev hooks over the immutable, running backend image.

Uses exported source from that image, strict one-occurrence patch anchors, a
content-addressed S3 overlay, and a read-only Fargate canary before service update.
The unrelated local backend working tree is never copied into this release.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import io
import json
from pathlib import Path
import secrets
import subprocess
import zipfile

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BOOTSTRAP = '''import boto3,hashlib,io,os,shutil,sys,zipfile
raw=boto3.client('s3').get_object(Bucket=os.environ['JEV_BUNDLE_BUCKET'],Key=os.environ['JEV_BUNDLE_KEY'])['Body'].read()
if hashlib.sha256(raw).hexdigest()!=os.environ['JEV_BUNDLE_SHA256']: raise RuntimeError('Jev overlay checksum mismatch')
zipfile.ZipFile(io.BytesIO(raw)).extractall('/app')
for name in ('training_labels.csv','validation_labels.csv','eval_labels.csv'):
 shutil.copyfile('/app/jev_reference/'+name,'/data/'+name)
module='paper_monitor.jev_backend_smoke' if '--check' in sys.argv else 'app.scripts.serve'
os.execv(sys.executable,[sys.executable,'-m',module])'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Backend source has drifted from the reviewed patch anchor: '+old[:80])
    return text.replace(old, new, 1)


def patch_sources(base):
    files = dict(base)
    patches = {
        'app/main.py': [('app.include_router(papers.router)', 'from app.api import jev\napp.include_router(jev.router)\napp.include_router(papers.router)')],
        'app/services/modular_rag_service.py': [
            ('    _trace(state, "routing", query_type=query_type, mode=mode)',
             '    _trace(state, "routing", query_type=query_type, mode=mode)\n    from app.services.jev_advisory_service import route_advice\n    route_advice(state)'),
            ('    _trace(state, "demonstrate", model=model, context_chars=len(context_blocks))',
             '    _trace(state, "demonstrate", model=model, context_chars=len(context_blocks))\n    from app.services.jev_advisory_service import check_answer\n    check_answer(state)')],
        'app/services/review_queue.py': [
            ('    stage1_ordinal: int | None', '    stage1_ordinal: int | None\n    jev_advice: dict | None = None'),
            ('        return out[offset : offset + limit]\n    return out',
             '        return out[offset : offset + limit]\n    from app.services.jev_advisory_service import review_advice\n    if not include_confirmed:\n        review_advice(out, session)\n    return out')],
        'app/api/review_queue.py': [
            ('    stage1_ordinal: int | None = None', '    stage1_ordinal: int | None = None\n    jev_advice: dict | None = None'),
            ('            rag_status=rag_status,', '            rag_status=rag_status,\n            jev_advice=None if blinded else item.jev_advice,')],
        'app/services/entity_extractor.py': [
            ('    session.add_all(rows)\n    session.flush()\n    return rows',
             '    session.add_all(rows)\n    session.flush()\n    from app.services.jev_advisory_service import graph_advice\n    graph_advice(session, paper, rows)\n    return rows')],
    }
    for path, replacements in patches.items():
        for old, new in replacements:
            files[path] = replace_once(files[path], old, new)
    for path in ('app/services/jev_advisory_service.py', 'app/api/jev.py'):
        files[path] = (REPO/'backend'/path).read_text()
    for path in sorted((ROOT/'paper_monitor').glob('*.py')):
        files[str(path.relative_to(ROOT))] = path.read_text()
    for path, content in files.items():
        compile(content, path, 'exec')
    return files


def build_overlay(base):
    files = patch_sources(base)
    # Restore the repository's existing reference boundaries, never a dirty label edit.
    for name in ('training_labels.csv', 'validation_labels.csv', 'eval_labels.csv'):
        path = 'data/'+name
        content = (REPO/path).read_bytes()
        committed = subprocess.check_output(['git', 'show', 'HEAD:'+path], cwd=REPO)
        if content != committed:
            raise ValueError('Review boundary file has uncommitted changes: '+path)
        files['jev_reference/'+name] = content.decode()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, content in sorted(files.items()):
            z.writestr(zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0)), content.encode())
    return files, archive.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='pas-sdl0-dev')
    parser.add_argument('--region', default='ca-central-1')
    parser.add_argument('--cluster', default='paper-attribution-dev-cluster')
    parser.add_argument('--service', default='paper-attribution-dev-backend-svc')
    parser.add_argument('--bucket', default='paper-attribution-artifacts-dev-247893369214')
    parser.add_argument('--base-task', default='paper-attribution-pas-dev-backend:2')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--promote-canary', help='Promote only after this canary task stopped successfully')
    args = parser.parse_args()
    build = ROOT/'deploy/build'
    base = json.loads((build/'jev-backend-base.json').read_text())
    origin = json.loads((build/'jev-backend-base-origin.json').read_text())
    if origin['files'] != {p: hashlib.sha256(t.encode()).hexdigest() for p, t in base.items()}:
        raise ValueError('Exported backend source no longer matches its provenance')
    files, bundle = build_overlay(base)
    sha = hashlib.sha256(bundle).hexdigest()
    (build/'jev-backend.patch').write_text(''.join(''.join(difflib.unified_diff(base.get(p, '').splitlines(True), c.splitlines(True),
        fromfile=p+' (deployed base)', tofile=p+' (Jev overlay)')) for p, c in files.items() if p.startswith('app/')))
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ecs, iam, ssm, s3 = [session.client(n) for n in ('ecs', 'iam', 'ssm', 's3')]
    service = ecs.describe_services(cluster=args.cluster, services=[args.service])['services'][0]
    if args.promote_canary:
        release = json.loads((build/'jev-backend-release.json').read_text())
        if release['sha256'] != sha or release['canary_task'] != args.promote_canary:
            raise ValueError('Current source or canary differs from the prepared release')
        task = ecs.describe_tasks(cluster=args.cluster, tasks=[args.promote_canary])['tasks'][0]
        if task['lastStatus'] != 'STOPPED' or task['containers'][0].get('exitCode') != 0 or task['taskDefinitionArn'] != release['task_definition']:
            raise ValueError('Canary has not passed on this exact task definition')
        if service['taskDefinition'] != release['previous_task']:
            raise ValueError('Backend changed concurrently; reconcile before promotion')
        ecs.update_service(cluster=args.cluster, service=args.service, taskDefinition=release['task_definition'])
        print(json.dumps({'service_update_requested': True, **release}))
        return
    print(json.dumps({'sha256': sha, 'patch': str(build/'jev-backend.patch'), 'files': len(files)}))
    if not args.apply:
        return
    task = ecs.describe_task_definition(taskDefinition=args.base_task)['taskDefinition']
    current = ecs.describe_task_definition(taskDefinition=service['taskDefinition'])['taskDefinition']
    def immutable_image(image):
        if '@sha256:' in image:
            return image
        repository, tag = image.split('/', 1)[1].rsplit(':', 1)
        digest = session.client('ecr').describe_images(repositoryName=repository, imageIds=[{'imageTag': tag}])['imageDetails'][0]['imageDigest']
        return image.rsplit(':', 1)[0]+'@'+digest
    image = immutable_image(task['containerDefinitions'][0]['image'])
    if image != origin['base_image'] or immutable_image(current['containerDefinitions'][0]['image']) != image:
        raise ValueError('The image differs from the image used to export the reviewed source')
    account = session.client('sts').get_caller_identity()['Account']
    key = f'author-monitor/jev-backend/releases/{sha}.zip'
    admin_parameter = '/paper-attribution-dev-author-monitor/jev-admin-key'
    try:
        ssm.get_parameter(Name=admin_parameter)
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'ParameterNotFound':
            raise
        ssm.put_parameter(Name=admin_parameter, Type='SecureString', Value=secrets.token_urlsafe(36), Description='PAS Jev operator-only API credential')
    statements = [
        {'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': f'arn:aws:s3:::{args.bucket}/author-monitor/jev-backend/releases/*'},
        {'Effect': 'Allow', 'Action': ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem'],
         'Resource': f'arn:aws:dynamodb:{args.region}:{account}:table/paper-attribution-dev-slack'},
        {'Effect': 'Allow', 'Action': 'ssm:GetParameter', 'Resource': f'arn:aws:ssm:{args.region}:{account}:parameter/paper-attribution-dev-author-monitor/jev'}]
    iam.put_role_policy(RoleName=task['taskRoleArn'].rsplit('/', 1)[-1], PolicyName='JevAdvisory',
        PolicyDocument=json.dumps({'Version': '2012-10-17', 'Statement': statements}))
    iam.put_role_policy(RoleName=task['executionRoleArn'].rsplit('/', 1)[-1], PolicyName='JevOperatorCredential',
        PolicyDocument=json.dumps({'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Action': 'ssm:GetParameters',
            'Resource': f'arn:aws:ssm:{args.region}:{account}:parameter{admin_parameter}'}]}))
    s3.put_object(Bucket=args.bucket, Key=key, Body=bundle, ServerSideEncryption='AES256')
    allowed = ecs.meta.service_model.operation_model('RegisterTaskDefinition').input_shape.members
    revised = {k: copy.deepcopy(v) for k, v in current.items() if k in allowed}
    container = revised['containerDefinitions'][0]
    container['image'] = image
    env = {e['name']: e['value'] for e in container.get('environment', [])}
    env.update(JEV_MODE='shadow', JEV_CONFIG_PARAMETER='/paper-attribution-dev-author-monitor/jev',
        JEV_BUNDLE_BUCKET=args.bucket, JEV_BUNDLE_KEY=key, JEV_BUNDLE_SHA256=sha,
        SLACK_TABLE='paper-attribution-dev-slack', JEV_DAILY_CALL_LIMIT='20')
    container['environment'] = [{'name': k, 'value': v} for k, v in env.items()]
    container['secrets'] = [s for s in container.get('secrets', []) if s['name'] != 'JEV_ADMIN_KEY'] + [
        {'name': 'JEV_ADMIN_KEY', 'valueFrom': f'arn:aws:ssm:{args.region}:{account}:parameter{admin_parameter}'}]
    container['command'] = ['python', '-c', BOOTSTRAP]
    arn = ecs.register_task_definition(**revised)['taskDefinition']['taskDefinitionArn']
    started = ecs.run_task(cluster=args.cluster, taskDefinition=arn, launchType='FARGATE',
        networkConfiguration=service['networkConfiguration'],
        overrides={'containerOverrides': [{'name': container['name'], 'command': ['python', '-c', BOOTSTRAP, '--check']}]})
    if started.get('failures'):
        raise RuntimeError('Jev backend canary failed to start')
    release = {'previous_task': service['taskDefinition'], 'task_definition': arn, 'canary_task': started['tasks'][0]['taskArn'],
               'sha256': sha, 'admin_parameter': admin_parameter,
               'reference_boundaries': {p: hashlib.sha256(c.encode()).hexdigest() for p, c in files.items() if p.startswith('jev_reference/')},
               'reference_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()}
    (build/'jev-backend-release.json').write_text(json.dumps(release, indent=2)+'\n')
    print(json.dumps(release))


if __name__ == '__main__':
    main()
