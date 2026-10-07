"""One-time local installer: hidden input -> encrypted AWS SSM, never chat/logs."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_monitor.slack_app import api  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', default='pas-sdl0-dev')
    ap.add_argument('--region', default='ca-central-1')
    ap.add_argument('--stack', default='paper-attribution-dev-slack')
    ap.add_argument('--new-code', action='store_true', help='Keep stored credentials; issue another channel connection code')
    args = ap.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ssm = session.client('ssm')
    parameter = '/' + args.stack + '/credentials'
    if args.new_code:
        config = json.loads(ssm.get_parameter(Name=parameter, WithDecryption=True)['Parameter']['Value'])
    else:
        print('Paste the Bot User OAuth Token from OAuth & Permissions, then the Signing Secret from Basic Information. Inputs are hidden.')
        config = {'bot_token': getpass.getpass('Bot token (xoxb-…): ').strip(),
                  'signing_secret': getpass.getpass('Signing secret: ').strip()}
        if not config['bot_token'].startswith('xoxb-') or len(config['signing_secret']) < 20:
            raise SystemExit('Invalid token/secret format; nothing saved.')
    identity = api(config['bot_token'], 'auth.test', {})
    config['team_id'] = identity['team_id']
    table = session.resource('dynamodb').Table(args.stack)
    item = table.get_item(Key={'pk': 'settings'}, ConsistentRead=True).get('Item')
    settings = json.loads(item['payload']) if item else {}
    if settings.get('team_id') and settings['team_id'] != identity['team_id']:
        raise SystemExit('A different workspace is already configured. No credentials changed.')
    code = secrets.token_hex(6).upper()
    settings.update(team_id=identity['team_id'], connect_hash=hashlib.sha256(code.encode()).hexdigest(),
                    connect_expires=int(time.time()) + 3600)
    kwargs = {'Item': {'pk': 'settings', 'payload': json.dumps(settings), 'version': time.time_ns()}}
    if item:
        kwargs.update(ConditionExpression='#v = :v', ExpressionAttributeNames={'#v': 'version'}, ExpressionAttributeValues={':v': item['version']})
    else:
        kwargs['ConditionExpression'] = 'attribute_not_exists(pk)'
    # Validate identity before storing either secret; never echo tokens or API payloads.
    ssm.put_parameter(Name=parameter, Type='SecureString', Value=json.dumps(config), Overwrite=True)
    table.put_item(**kwargs)
    print(f"Verified Slack workspace: {identity.get('team', identity['team_id'])} ({identity['team_id']}). Credentials saved encrypted in AWS.")
    print('In Slack, use /papers anywhere; all messages will go only to your private conversation:')
    print('  1. /papers connect ' + code)
    print('  2. /papers test')
    print('  3. After the real-paper preview succeeds: /papers start')
    print('The connection code expires in one hour. /papers pause stops notifications; collection continues.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Setup failed (' + type(exc).__name__ + '). Check the credentials, AWS login and network; no secret values are printed.', file=sys.stderr)
        raise SystemExit(1) from None
