"""Narrow runtime storage lifecycle without replacing unrelated bucket rules."""
import argparse
import copy
import json
from pathlib import Path

import boto3

ARCHIVE_PREFIXES = ('database-backups/', 'etl-runs/', 'manifests/', 'raw/',
                    'workspace-backups/', 'model-snapshots/', 'pipeline-runs/', 'logs/')


def rules(existing):
    result = []
    managed = {'archive-' + prefix.rstrip('/') for prefix in ARCHIVE_PREFIXES}
    managed.update({'monitor-state-versions', 'monitor-mail-versions', 'monitor-verification'})
    for rule in copy.deepcopy(existing):
        if rule['ID'] in ('transition-to-ia', 'transition-to-glacier'):
            if rule.get('Filter', {}) not in ({}, {'Prefix': ''}) or rule.get('Prefix', '') != '':
                raise ValueError('Unexpected lifecycle filter; review before replacing')
            continue
        if rule['ID'] in managed:
            continue
        result.append(rule)
    for prefix in ARCHIVE_PREFIXES:
        result.append({'ID': 'archive-' + prefix.rstrip('/'), 'Status': 'Enabled',
            'Filter': {'Prefix': prefix}, 'Transitions': [
                {'Days': 90, 'StorageClass': 'STANDARD_IA'},
                {'Days': 365, 'StorageClass': 'GLACIER'}]})
    result.extend([
        {'ID': 'monitor-verification', 'Status': 'Enabled',
         'Filter': {'Prefix': 'author-monitor/verification/'}, 'Expiration': {'Days': 7},
         'NoncurrentVersionExpiration': {'NoncurrentDays': 7}},
        {'ID': 'monitor-state-versions', 'Status': 'Enabled',
         'Filter': {'Prefix': 'author-monitor/production/state.db'},
         'NoncurrentVersionExpiration': {'NoncurrentDays': 7, 'NewerNoncurrentVersions': 10}},
        {'ID': 'monitor-mail-versions', 'Status': 'Enabled',
         'Filter': {'Prefix': 'author-monitor/production/mail-raw/'},
         'NoncurrentVersionExpiration': {'NoncurrentDays': 7},
         'Expiration': {'ExpiredObjectDeleteMarker': True}},
    ])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='pas-sdl0-dev')
    parser.add_argument('--region', default='ca-central-1')
    parser.add_argument('--bucket', default='paper-attribution-artifacts-dev-247893369214')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    s3 = boto3.Session(profile_name=args.profile, region_name=args.region).client('s3')
    before = s3.get_bucket_lifecycle_configuration(Bucket=args.bucket)
    after = {'Rules': rules(before['Rules'])}
    build = Path(__file__).parent / 'build'
    build.mkdir(exist_ok=True)
    (build / 'storage-lifecycle-before.json').write_text(json.dumps(before, indent=2))
    (build / 'storage-lifecycle-after.json').write_text(json.dumps(after, indent=2))
    print(json.dumps({'rules': len(after['Rules']), 'state_retention': '7 days and at least 10 previous versions',
                      'runtime_archival': False, 'apply': args.apply}))
    if args.apply:
        s3.put_bucket_lifecycle_configuration(Bucket=args.bucket, LifecycleConfiguration=after,
            TransitionDefaultMinimumObjectSize=before.get('TransitionDefaultMinimumObjectSize', 'all_storage_classes_128K'))
        actual = s3.get_bucket_lifecycle_configuration(Bucket=args.bucket)
        if actual['Rules'] != after['Rules']:
            raise RuntimeError('Lifecycle readback differs from the reviewed rules')


if __name__ == '__main__':
    main()
