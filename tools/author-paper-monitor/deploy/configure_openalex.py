"""Configure a free OpenAlex key without exposing it in chat or shell history."""
import argparse
import getpass
import os
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_monitor import openalex  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', default='pas-sdl0-dev')
    args = ap.parse_args()
    key = getpass.getpass('OpenAlex API key (hidden): ').strip()
    if not key:
        raise SystemExit('No key supplied; nothing changed.')
    os.environ['OPENALEX_API_KEY'] = key
    result = openalex.author_by_orcid('0000-0002-8277-4434')
    if not result or openalex.short_id(result['id']) != 'A5071495561':
        raise SystemExit('API validation failed; nothing saved.')
    boto3.Session(profile_name=args.profile, region_name='ca-central-1').client('ssm').put_parameter(
        Name='/paper-attribution-dev-author-monitor/openalex-api-key', Value=key, Type='SecureString', Overwrite=True)
    print('Key verified and stored encrypted in AWS. The collector and Slack author search use it on their next run.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Configuration failed (' + type(exc).__name__ + '); no secret values are printed.', file=sys.stderr)
        raise SystemExit(1) from None
