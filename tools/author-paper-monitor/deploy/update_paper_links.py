"""Patch only card rendering in the existing Slack/collector release bundles."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]


def main():
    aws=boto3.Session(profile_name='pas-sdl0-dev',region_name='ca-central-1');s3=aws.client('s3');cfn=aws.client('cloudformation')
    source=(ROOT/'paper_monitor/slack_app.py').read_bytes();records=[]
    for stack in ['paper-attribution-dev-slack','paper-attribution-dev-author-monitor']:
        doc=cfn.get_template(StackName=stack,TemplateStage='Original')['TemplateBody']
        if isinstance(doc,str):doc=json.loads(doc)
        resources=doc['Resources']
        if stack.endswith('-slack'):
            locations=[v['Properties']['Code'] for v in resources.values() if v['Type']=='AWS::Lambda::Function']
            bucket,key=locations[0]['S3Bucket'],locations[0]['S3Key'];prefix='author-monitor/slack-releases/'
        else:
            task=next(v['Properties'] for v in resources.values() if v['Type']=='AWS::ECS::TaskDefinition')
            env={v['Name']:v['Value'] for v in task['ContainerDefinitions'][0]['Environment']}
            bucket,key=env['MONITOR_BUCKET'],env['MONITOR_BUNDLE'];prefix='author-monitor/releases/'
        raw=s3.get_object(Bucket=bucket,Key=key)['Body'].read()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:files={n:archive.read(n) for n in archive.namelist()}
        files['paper_monitor/slack_app.py']=source
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
            for n,data in sorted(files.items()):archive.writestr(zipfile.ZipInfo(n,date_time=(2026,1,1,0,0,0)),data)
        blob=out.getvalue();sha=hashlib.sha256(blob).hexdigest();newkey=prefix+sha+'.zip'
        s3.put_object(Bucket=bucket,Key=newkey,Body=blob,ServerSideEncryption='AES256')
        if stack.endswith('-slack'):
            for code in locations:code['S3Key']=newkey
        else:
            for entry in task['ContainerDefinitions'][0]['Environment']:
                if entry['Name']=='MONITOR_BUNDLE':entry['Value']=newkey
                if entry['Name']=='MONITOR_SHA256':entry['Value']=sha
        cfn.update_stack(StackName=stack,TemplateBody=json.dumps(doc),Capabilities=['CAPABILITY_IAM'])
        records.append({'stack':stack,'previous_bundle':key,'bundle':newkey,'sha256':sha,'only_changed_module':'paper_monitor/slack_app.py'})
    (ROOT/'deploy/build/paper-links-release.json').write_text(json.dumps(records,indent=2));print(json.dumps(records))


if __name__=='__main__':main()
