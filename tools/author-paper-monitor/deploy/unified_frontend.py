"""Publish the unified PAS UI while keeping reports and old assets protected."""
import hashlib
import json
import mimetypes
import time
from reading_aws import BUILD, REPO, ROOT, aws_session

BUCKET='paper-attribution-frontend-dev-247893369214'
DISTRIBUTION='E1WXNS5EAM25VU'


def main():
    aws=aws_session()
    s3,cf=aws.client('s3'),aws.client('cloudfront')
    s3.head_object(Bucket=BUCKET,Key='protected-legacy/index.html')
    policy=json.loads(s3.get_bucket_policy(Bucket=BUCKET)['Policy'])
    snapshot=BUILD/'unified-frontend-before-policy.json'
    if not snapshot.exists():snapshot.write_text(json.dumps(policy,indent=2))
    # Allow only UI code, never public/data or the protected original reports.
    statement=next(s for s in policy['Statement'] if s.get('Principal',{}).get('Service')=='cloudfront.amazonaws.com')
    resources=statement['Resource'];resources=[resources] if isinstance(resources,str) else resources
    for suffix in ['/assets/*.js','/assets/*.css']:
        value='arn:aws:s3:::'+BUCKET+suffix
        if value not in resources:resources.append(value)
    statement['Resource']=resources
    s3.put_bucket_policy(Bucket=BUCKET,Policy=json.dumps(policy))
    artifacts={}
    for directory,prefix,entry in [('dist','', 'index.html'),('dist-reading','reading/','reading.html')]:
        path=REPO/'frontend'/directory
        candidates=list((path/'assets').glob('*.js'))+list((path/'assets').glob('*.css'))+[path/entry]
        for file in candidates:
            key=prefix+('index.html' if file.name==entry else 'assets/'+file.name)
            raw=file.read_bytes()
            s3.put_object(Bucket=BUCKET,Key=key,Body=raw,ContentType=mimetypes.guess_type(key)[0] or 'application/octet-stream',CacheControl='no-store' if key.endswith('.html') else 'public,max-age=31536000,immutable')
            artifacts[key]=hashlib.sha256(raw).hexdigest()
    name='paper-attribution-dev-spa-routing'
    before=cf.get_function(Name=name,Stage='DEVELOPMENT')
    if not (BUILD/'unified-frontend-before-routing.js').exists():
        (BUILD/'unified-frontend-before-routing.js').write_bytes(before['FunctionCode'].read())
    config=cf.describe_function(Name=name,Stage='DEVELOPMENT')['FunctionSummary']['FunctionConfig']
    result=cf.update_function(Name=name,IfMatch=before['ETag'],FunctionConfig=config,FunctionCode=(ROOT/'deploy/access/routing.js').read_bytes())
    cf.publish_function(Name=name,IfMatch=result['ETag'])
    invalid=cf.create_invalidation(DistributionId=DISTRIBUTION,InvalidationBatch={'Paths':{'Quantity':1,'Items':['/*']},'CallerReference':'unified-pas-'+str(time.time_ns())})
    result={'url':'https://d1ai8ldqsh81fz.cloudfront.net/','artifacts':artifacts,'invalidation':invalid['Invalidation']['Id']}
    (BUILD/'unified-frontend-release.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()
