"""Read-only Graph verification and encrypted AWS setup; never enables the schedule.

Run locally with AWS CLI/SSO. No production credentials enter Codespaces.
The first collection imports the folder snapshot with existing PAS deduplication;
verification deliberately does not save a delta cursor or discard those papers.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import getpass
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_monitor import scholar_graph
from paper_monitor.authors import Author
from paper_monitor.scholar_email import MailboxError
from paper_monitor.store import Store


def aws(args, service, operation, payload):
    result = subprocess.run(['aws', '--profile', args.profile, '--region', args.region,
        service, operation, '--cli-input-json', 'file:///dev/stdin', '--output', 'json'],
        input=json.dumps(payload), text=True, capture_output=True)
    if result.returncode:
        raise ValueError('AWS request failed; check SSO and parameter permissions')
    return json.loads(result.stdout or '{}')


def active_authors(args):
    rows, payload = [], {'TableName': args.table, 'ConsistentRead': True,
        'FilterExpression': 'begins_with(pk, :prefix)',
        'ExpressionAttributeValues': {':prefix': {'S': 'author:'}}}
    while True:
        page = aws(args, 'dynamodb', 'scan', payload)
        rows.extend(json.loads(row['payload']['S']) for row in page['Items'])
        if not page.get('LastEvaluatedKey'):
            break
        payload['ExclusiveStartKey'] = page['LastEvaluatedKey']
    authors = [Author(row['name']) for row in rows if row.get('status') == 'active']
    if not authors:
        raise ValueError('No active authors; configuration was not saved')
    return authors


def verify(config, authors):
    scholar_graph.validate_config(config, verified=False)
    token = scholar_graph.access_token(config)
    folder = scholar_graph.request(scholar_graph.folder_url(config) + '?$select=id,displayName', token=token)
    if folder.get('displayName') != config['folder']:
        raise MailboxError('Configured folder ID does not match the expected folder name')
    verified = {**config, 'verified_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    with contextlib.closing(Store(Path(':memory:'))) as store:
        papers, cursor = scholar_graph.fetch_pending(store, authors, verified, token=token)
    counts = json.loads(cursor[1])
    verified['publication_sample_verified'] = bool(papers)
    return verified, {'mailbox_access_verified': True, 'parsed_papers': len(papers),
        'publication_sample_verified': bool(papers),
        'messages_scanned': counts['messages'], 'ignored_messages': counts['ignored'],
        'initial_mail_history': 'Folder snapshot will be imported with existing paper deduplication',
        'schedule_enabled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='pas-sdl0-dev')
    parser.add_argument('--region', default='ca-central-1')
    parser.add_argument('--table', default='paper-attribution-dev-slack')
    parser.add_argument('--parameter', default='/paper-attribution-dev-author-monitor/scholar-mailbox')
    parser.add_argument('--tenant-id', default='78aac226-2f03-4b4d-9037-b46d56c55210')
    parser.add_argument('--client-id', required=True)
    parser.add_argument('--mailbox', default='comms.acceleration@utoronto.ca')
    parser.add_argument('--folder', default='Google Scholar Alerts')
    parser.add_argument('--folder-id', required=True, help='Graph ID of the dedicated folder, from IT')
    parser.add_argument('--author-map', type=Path, help='JSON: Scholar display name -> active watchlist name')
    parser.add_argument('--save', action='store_true', help='Save verified credentials encrypted in AWS SSM')
    args = parser.parse_args()
    authors = active_authors(args)
    aliases = json.loads(args.author_map.read_text()) if args.author_map else {}
    if not isinstance(aliases, dict) or any(not isinstance(k, str) or v not in {a.name for a in authors}
                                           for k, v in aliases.items()):
        raise ValueError('Aliases must map to active watchlist names')
    if not sys.stdin.isatty():
        parser.error('Use a terminal for hidden client secret entry')
    config, report = verify({'provider': 'graph', 'tenant_id': args.tenant_id,
        'client_id': args.client_id, 'client_secret': getpass.getpass('Microsoft app client secret (hidden): ').strip(),
        'mailbox': args.mailbox, 'folder': args.folder, 'folder_id': args.folder_id,
        'author_aliases': aliases}, authors)
    if args.save:
        aws(args, 'ssm', 'put-parameter', {'Name': args.parameter, 'Type': 'SecureString',
                                        'Value': json.dumps(config), 'Overwrite': True})
    print(json.dumps({**report, 'saved_encrypted': args.save}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Configuration failed (' + type(exc).__name__ + '); credentials were not printed.', file=sys.stderr)
        raise SystemExit(1) from None
