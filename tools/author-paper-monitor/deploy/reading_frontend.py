"""Publish the isolated reader, preserving existing PAS frontend entries."""
import hashlib
import json
import mimetypes
from pathlib import Path
import time
import boto3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
DISTRIBUTION = 'E1WXNS5EAM25VU'
BUCKET = 'paper-attribution-frontend-dev-247893369214'


def main():
    session = boto3.Session(profile_name='pas-sdl0-dev', region_name='ca-central-1')
    cf, s3 = session.client('cloudfront'), session.client('s3')
    build = ROOT / 'deploy/build'
    config = cf.get_distribution_config(Id=DISTRIBUTION)
    doc = config['DistributionConfig']
    (build / 'reading-cloudfront-before.json').write_text(json.dumps(doc, indent=2))
    spa = next(a['FunctionARN'] for a in doc['DefaultCacheBehavior']['FunctionAssociations']['Items']
               if a['EventType'] == 'viewer-request').rsplit('/', 1)[-1]
    function = cf.get_function(Name=spa, Stage='DEVELOPMENT')
    code = function['FunctionCode'].read().decode()
    (build / 'reading-routing-before.js').write_text(code)
    if "'/reading/index.html'" not in code:
        marker = 'var uri = request.uri;'
        assert code.count(marker) == 1
        code = code.replace(marker, marker + "\n  if (uri === '/reading' || uri === '/reading/') { request.uri = '/reading/index.html'; return request; }", 1)
        details = cf.describe_function(Name=spa, Stage='DEVELOPMENT')['FunctionSummary']['FunctionConfig']
        changed = cf.update_function(Name=spa, IfMatch=function['ETag'], FunctionConfig=details, FunctionCode=code.encode())
        cf.publish_function(Name=spa, IfMatch=changed['ETag'])
    # Publishing an associated function can change the distribution ETag.
    config = cf.get_distribution_config(Id=DISTRIBUTION)
    doc = config['DistributionConfig']
    api = next(b for b in doc['CacheBehaviors']['Items'] if b['PathPattern'] == '/api/*')
    headers = api['ForwardedValues']['Headers']
    changed_config = False
    errors = doc.get('CustomErrorResponses', {}).get('Items', [])
    kept = [e for e in errors if not (e['ErrorCode'] == 404 and e.get('ResponseCode') == '200')]
    if kept != errors:
        doc['CustomErrorResponses'] = {'Quantity': len(kept), **({'Items': kept} if kept else {})}
        changed_config = True
    if 'X-PAS-Request' not in headers['Items']:
        headers['Items'].append('X-PAS-Request')
        headers['Quantity'] = len(headers['Items'])
        changed_config = True
    if changed_config:
        cf.update_distribution(Id=DISTRIBUTION, IfMatch=config['ETag'], DistributionConfig=doc)
    artifacts = {}
    for path in sorted((REPO / 'frontend/dist-reading').rglob('*')):
        if not path.is_file():
            continue
        relative = str(path.relative_to(REPO / 'frontend/dist-reading'))
        if relative != 'reading.html' and not relative.startswith('assets/'):
            continue
        key = 'reading/' + ('index.html' if relative == 'reading.html' else relative)
        data = path.read_bytes()
        s3.put_object(Bucket=BUCKET, Key=key, Body=data,
                      ContentType=mimetypes.guess_type(key)[0] or 'application/octet-stream',
                      CacheControl='no-cache' if key.endswith('.html') else 'public,max-age=31536000,immutable')
        artifacts[key] = hashlib.sha256(data).hexdigest()
    invalid = cf.create_invalidation(DistributionId=DISTRIBUTION, InvalidationBatch={
        'Paths': {'Quantity': 3, 'Items': ['/reading', '/reading/', '/reading/index.html']},
        'CallerReference': 'reading-' + str(time.time_ns())})
    result = {'artifacts': artifacts, 'invalidation': invalid['Invalidation']['Id'],
              'url': 'https://d1ai8ldqsh81fz.cloudfront.net/reading/'}
    (build / 'reading-frontend-release.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
