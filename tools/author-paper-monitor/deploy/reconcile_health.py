"""Resolve a lost watchdog Slack receipt only after inspecting the private message."""
import argparse
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_monitor import registry  # noqa: E402


def reconcile(current, receipt):
    if current.get('status') != 'sending':
        raise ValueError('Only an uncertain watchdog message can be reconciled')
    if receipt and not re.fullmatch(r'[0-9]+\.[0-9]+', receipt):
        raise ValueError('Expected the existing Slack message timestamp')
    current['status'] = 'posted' if receipt else 'retryable'
    if receipt:
        current['ts'] = receipt
    else:
        current['retry_after'] = 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', default='pas-sdl0-dev')
    ap.add_argument('--region', default='ca-central-1')
    ap.add_argument('--table', default='paper-attribution-dev-slack')
    decision = ap.add_mutually_exclusive_group(required=True)
    decision.add_argument('--receipt-ts', help='Timestamp of the message actually found in Slack')
    decision.add_argument('--retry', action='store_true', help='Only when confirmed absent from Slack')
    args = ap.parse_args()
    os.environ.update(AWS_PROFILE=args.profile, AWS_DEFAULT_REGION=args.region, SLACK_TABLE=args.table)
    registry.change('monitor-incident', lambda current: reconcile(current, args.receipt_ts))
    print('Watchdog receipt reconciled; next health check resumes automatically.')


if __name__ == '__main__':
    main()
