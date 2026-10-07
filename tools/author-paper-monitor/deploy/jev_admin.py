"""Use the private PAS Jev operator API without copying credentials into chat."""
import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request

import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'decisions', 'evaluate', 'feedback'])
    parser.add_argument('--profile', default='pas-sdl0-dev')
    parser.add_argument('--region', default='ca-central-1')
    parser.add_argument('--input', type=Path, help='Evaluation or feedback JSON; public metadata / paper IDs only')
    parser.add_argument('--decision-id', help='Required for feedback')
    args = parser.parse_args()
    if args.command in ('evaluate', 'feedback') and not args.input:
        parser.error('This command requires --input /path/to/request.json')
    path = '/'+args.command
    if args.command == 'feedback':
        if not args.decision_id or len(args.decision_id) != 64 or any(c not in '0123456789abcdef' for c in args.decision_id):
            parser.error('Feedback requires the 64-character decision ID')
        path = '/decisions/'+args.decision_id+'/feedback'
    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        key = session.client('ssm').get_parameter(Name='/paper-attribution-dev-author-monitor/jev-admin-key', WithDecryption=True)['Parameter']['Value']
        data = json.dumps(json.loads(args.input.read_text())).encode() if args.input else None
        request = urllib.request.Request('https://d1ai8ldqsh81fz.cloudfront.net/api/jev'+path, data=data,
            headers={'X-Jev-Key': key, 'Content-Type': 'application/json'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            result = json.load(response)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        status = str(exc.code) if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        print('Jev operator request failed: '+status)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
