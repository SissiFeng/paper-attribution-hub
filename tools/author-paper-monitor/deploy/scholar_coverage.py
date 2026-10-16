"""Export/import author-alert setup evidence; never creates Google subscriptions."""
import argparse
import csv
import json
import os
import sys
import urllib.parse
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_monitor import registry

FIELDS = ['person_id', 'name', 'watchlist_status', 'profile_url', 'alert_created',
          'subscription_confirmed', 'last_received_at', 'publication_messages']


def changes(path, authors):
    known = {r['person_id']: r for r in authors}
    updates, seen = [], set()
    with path.open(encoding='utf-8-sig', newline='') as source:
        for row in csv.DictReader(source):
            identifier = row.get('person_id')
            if identifier not in known or identifier in seen or row.get('name') != known[identifier]['name']:
                raise ValueError('Coverage rows must uniquely match the existing author ID and name')
            seen.add(identifier)
            values = {}
            for field in ('alert_created', 'subscription_confirmed'):
                value = row.get(field, '').strip().lower()
                if value not in ('', 'true', 'false', 'yes', 'no', '1', '0'):
                    raise ValueError('Coverage flags must be true or false')
                values[field] = value in ('true', 'yes', '1')
            profile = row.get('profile_url', '').strip()
            if profile:
                url = urllib.parse.urlsplit(profile)
                if url.scheme != 'https' or url.netloc != 'scholar.google.com' or url.path != '/citations' or not urllib.parse.parse_qs(url.query).get('user'):
                    raise ValueError('Use the Google Scholar author profile, not a topic-search alert')
            if values['alert_created'] and not profile or values['subscription_confirmed'] and not values['alert_created']:
                raise ValueError('Confirm the author profile and alert creation before marking confirmation')
            values['profile_url'] = profile
            updates.append((identifier, values))
    return updates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='pas-sdl0-dev')
    parser.add_argument('--region', default='ca-central-1')
    parser.add_argument('--table', default='paper-attribution-dev-slack')
    parser.add_argument('--export', type=Path)
    parser.add_argument('--import-csv', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if bool(args.export) == bool(args.import_csv):
        parser.error('Choose --export or --import-csv')
    registry.session = lambda: boto3.Session(profile_name=args.profile, region_name=args.region)
    os.environ['SLACK_TABLE'] = args.table
    authors = registry.authors()
    if args.export:
        args.export.parent.mkdir(parents=True, exist_ok=True)
        with args.export.open('w', encoding='utf-8-sig', newline='') as dest:
            writer = csv.DictWriter(dest, fieldnames=FIELDS)
            writer.writeheader()
            for author in authors:
                writer.writerow({**{k: v for k, v in author.get('scholar', {}).items() if k in FIELDS},
                    'person_id': author['person_id'], 'name': author['name'], 'watchlist_status': author['status']})
        print(json.dumps({'exported_authors': len(authors), 'path': str(args.export)}))
    else:
        updates = changes(args.import_csv, authors)
        if args.apply:
            for identifier, values in updates:
                registry.change('author:' + identifier,
                    lambda current, values=values: current.setdefault('scholar', {}).update(values))
        print(json.dumps({'validated_rows': len(updates), 'applied': args.apply,
                          'google_subscriptions_created': False}))


if __name__ == '__main__':
    main()
