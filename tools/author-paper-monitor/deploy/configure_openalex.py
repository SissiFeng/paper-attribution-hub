"""Configure a free OpenAlex key without exposing it in chat or shell history."""
import argparse
import getpass
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_monitor import openalex  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', default='pas-sdl0-dev')
    args = ap.parse_args()
    key = getpass.getpass('OpenAlex API key (hidden): ').strip()
    if not key:
        raise SystemExit('No key supplied; nothing changed.')
    openalex.validate_api_key(key)
    # Keep credentials out of process arguments, shell history and Codespaces.
    subprocess.run(
        ['aws', '--profile', args.profile, '--region', 'ca-central-1', 'ssm',
         'put-parameter', '--cli-input-json', 'file:///dev/stdin'],
        input=json.dumps({'Name': '/paper-attribution-dev-author-monitor/openalex-api-key',
                          'Value': key, 'Type': 'SecureString', 'Overwrite': True}),
        text=True, capture_output=True, check=True,
    )
    print('Two cursor pages verified; key stored encrypted in AWS. The collector and Slack author search use it on their next run.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Configuration failed (' + type(exc).__name__ + '); no secret values are printed.', file=sys.stderr)
        raise SystemExit(1) from None
