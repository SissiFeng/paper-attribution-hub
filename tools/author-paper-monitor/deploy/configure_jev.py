"""Configure Jev using hidden input; verify one public paper before saving to SSM."""
from __future__ import annotations

import argparse
import contextlib
import getpass
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_monitor import jev
from paper_monitor.models import Paper


def verify_and_save(session, config, parameter, bucket, *, save):
    # Real, public metadata from the existing catalogue; no private Slack data.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/'state.db'
        session.client('s3').download_file(bucket, 'author-monitor/production/state.db', str(path))
        with contextlib.closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True)) as db:
            row = db.execute("SELECT data FROM papers ORDER BY json_extract(data,'$.date') DESC LIMIT 1").fetchone()
        if not row:
            raise ValueError('The monitoring catalogue has no paper for a connection check')
        result = jev.decide(jev.request_for(Paper(**json.loads(row[0])), config), config['api_key'])
    if save:
        session.client('ssm').put_parameter(Name=parameter, Type='SecureString',
            Value=json.dumps(config), Overwrite=True,
            Description='AC Papers Jev shadow evaluation; API key, pinned model and public research focus')
    return {'status': 'verified_and_saved' if save else 'verified', 'parameter': parameter,
            'model': result['model'], 'usage': result['usage'], 'mode': 'shadow',
            'note': 'One live contract check; scientific accuracy and calibration have not been evaluated.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='pas-sdl0-dev')
    parser.add_argument('--region', default='ca-central-1')
    parser.add_argument('--stack', default='paper-attribution-dev-author-monitor')
    parser.add_argument('--bucket', default='paper-attribution-artifacts-dev-247893369214')
    parser.add_argument('--focus-file', type=Path, help='Optional public research focus, 1–2000 characters')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--status', action='store_true', help='Read configuration status without calling Jev or showing secrets')
    mode.add_argument('--check', action='store_true', help='Make one live request using the saved key; do not change configuration')
    args = parser.parse_args(argv)
    parameter = f'/{args.stack}/jev'
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    try:
        session.client('sts').get_caller_identity()  # Fail before asking for a key if SSO expired.
        if args.status or args.check:
            try:
                raw = session.client('ssm').get_parameter(Name=parameter, WithDecryption=True)
            except ClientError as exc:
                if exc.response['Error']['Code'] != 'ParameterNotFound':
                    raise
                print(json.dumps({'status': 'needs_configuration', 'parameter': parameter}))
                return 0 if args.status else 1
            config = json.loads(raw['Parameter']['Value'])
            if config.get('model') != jev.MODEL or not isinstance(config.get('api_key'), str) or not config['api_key'].strip():
                raise ValueError('Invalid saved configuration')
            if args.status:
                print(json.dumps({'status': 'configured_not_checked', 'parameter': parameter, 'model': config['model']}))
                return 0
        else:
            focus = args.focus_file.read_text().strip() if args.focus_file else jev.DEFAULT_FOCUS
            if not 1 <= len(focus) <= 2000:
                parser.error('Research focus must contain 1–2000 characters')
            if not sys.stdin.isatty():
                parser.error('Run this command in your terminal for hidden key entry; never pass a key as an argument')
            key = getpass.getpass('TypeSafe API key (hidden; one live check before encrypted storage): ').strip()
            if not key:
                parser.error('No key entered; nothing saved')
            config = {'model': jev.MODEL, 'focus': focus, 'api_key': key}
        print(json.dumps(verify_and_save(session, config, parameter, args.bucket, save=not args.check)))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        # Neither API exception bodies nor SSM values belong in terminal history/logs.
        print('Jev configuration failed (' + type(exc).__name__ + '). No unverified key was saved.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
