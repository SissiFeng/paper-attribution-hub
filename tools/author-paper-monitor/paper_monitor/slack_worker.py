"""Slow Slack work runs off the request path; ambiguous posts are never replayed."""
from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path

from . import openalex, registry, slack_app, subscriptions
from .models import Paper


def preview_papers():
    import boto3
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'state.db'
        boto3.client('s3').download_file(os.environ['MONITOR_BUCKET'], 'author-monitor/production/state.db', str(path))
        with contextlib.closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True)) as db:
            rows = db.execute("SELECT data FROM papers ORDER BY json_extract(data,'$.date') DESC LIMIT 3").fetchall()
        return [Paper(**json.loads(row[0])) for row in rows]


def shadow_report():
    from botocore.exceptions import ClientError
    try:
        result = registry.client('s3').get_object(Bucket=os.environ['MONITOR_BUCKET'],
            Key='author-monitor/production/outbox/jev-shadow.json')
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'NoSuchKey':
            return {}
        raise
    with contextlib.closing(result['Body']) as body:
        raw = body.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError('Jev report too large for a Slack preview')
    return json.loads(raw)


def process(kind, data, key, config):
    token = config['bot_token']
    if kind == 'connect_dm':
        settings = registry.get('settings')
        if settings.get('owner_id') != data['user'] or settings.get('connection_key') != key:
            raise ValueError('Connection changed before processing')
        result = slack_app.api(token, 'conversations.open', {'users': data['user']})
        channel = result['channel']['id']
        if not channel.startswith('D'):
            raise ValueError('Expected a private direct conversation')
        def connected(current):
            if current.get('connection_key') != key or current.get('owner_id') != data['user']:
                raise ValueError('Connection changed')
            current['channel_id'] = channel
        registry.change('settings', connected)
        slack_app.api(token, 'chat.postMessage', {'channel': channel,
            'text': 'AC Papers is connected privately to you. Run `/papers test` for a real-paper preview, then `/papers start` to enable paper updates. No group channel will receive messages.'})
        slack_app.api(token, 'views.publish', {'user_id': data['user'],
            'view': slack_app.home(registry.get('settings'), registry.authors())})
    elif kind == 'home':
        subscriptions.welcome(data['user'], token)
        slack_app.api(token, 'views.publish', {'user_id': data['user'],
            'view': slack_app.home(subscriptions.view(data['user']), registry.authors(), data.get('page', 0))})
    elif kind in ('jev_review', 'jev_decisions'):
        personal = subscriptions.request(data['user'])
        if data.get('channel') and personal.get('channel_id') != data['channel']:
            raise ValueError('Connection changed before Jev review')
        personal = subscriptions.connect(data['user'], token)
        data = {**data, 'channel': personal['channel_id']}
        settings = subscriptions.view(data['user'])
        if kind == 'jev_decisions':
            from .jev_ledger import journal
            slack_app.api(token, 'chat.postMessage', {'channel': data['channel'], **slack_app.decisions_message(journal().recent(50))})
            return
        report = shadow_report()
        scored = sorted((p for p in report.get('items', []) if p['status'] == 'ok'), key=lambda p: p['suggested_rank'])
        state = settings.get('jev_shadow', {}).get('status')
        if not scored or state in ('off', 'needs_configuration'):
            slack_app.api(token, 'chat.postMessage', {'channel': data['channel'],
                'text': slack_app.jev_status(settings) + ' No evaluated suggestions to show yet. Regular collection, paper storage and your private updates continue as usual.'})
            return
        top = scored[:3]
        text = (f"*Jev · experimental reading suggestions*\n{report['scored']} of {report['papers']} papers evaluated; showing the top {len(top)} of the evaluated subset. "
                'Unevaluated papers are not treated as irrelevant.\nRegular digest order stays unchanged. Suggestions need human review; probability calibration has not been verified.\n'
                f"Snapshot: {report.get('generated_at', 'unknown')}. Details are in the thread.")
        root = slack_app.api(token, 'chat.postMessage', {'channel': data['channel'], 'text': text, 'blocks': [slack_app.section(text)]})
        registry.put('jev-preview:' + key, {'channel': data['channel'], 'ts': root['ts'], 'status': 'sending'})
        for item in top:
            paper = Paper(**{k: item[k] for k in ('title', 'abstract', 'url', 'date', 'authors', 'venue', 'tracked_authors', 'sources', 'doi', 'openalex_id')})
            time.sleep(1.1)
            slack_app.api(token, 'chat.postMessage', {'channel': data['channel'], 'thread_ts': root['ts'],
                **slack_app.shadow_card(paper, item['decision'])})
        registry.put('jev-preview:' + key, {'channel': data['channel'], 'ts': root['ts'], 'status': 'posted'})
    elif kind == 'preview':
        personal = subscriptions.request(data['user'])
        if data.get('channel') and personal.get('channel_id') != data['channel']:
            raise ValueError('Connection changed before preview')
        personal = subscriptions.connect(data['user'], token)
        data = {**data, 'channel': personal['channel_id']}
        papers = preview_papers()
        if not papers:
            raise ValueError('No real papers available yet; wait for the first collection')
        root = slack_app.api(token, 'chat.postMessage', {'channel': data['channel'], **slack_app.digest(papers, preview=True)})
        registry.put('preview:' + key, {'channel': data['channel'], 'ts': root['ts'], 'status': 'sending'})
        for p in papers:
            time.sleep(1.1)
            slack_app.api(token, 'chat.postMessage', {'channel': data['channel'], 'thread_ts': root['ts'], **slack_app.card(p)})
        def tested(current):
            if current.get('channel_id') == data['channel']:
                current['tested_channel'] = data['channel']
                current['last_test'] = int(time.time())
        registry.change(subscriptions.key(data['user']), tested)
        registry.put('preview:' + key, {'channel': data['channel'], 'ts': root['ts'], 'status': 'posted'})
    elif kind == 'feedback':
        registry.put(f"feedback:{data['paper']}:{data['user']}", {**data, 'updated_at': int(time.time())})
        if data.get('channel'):
            slack_app.api(token, 'chat.postEphemeral', {'channel': data['channel'], 'user': data['user'],
                'text': 'Thanks — your author-match report was saved for review.' if data['vote'] == 'paper_more'
                        else 'Thanks — your feedback was saved. This does not automatically hide papers.'})
    elif kind == 'lookup':
        registry.configure_openalex()
        query = data['query'].strip()
        orcid = query.removeprefix('https://orcid.org/').removeprefix('http://orcid.org/')
        if re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', orcid):
            author = openalex.author_by_orcid(orcid)
            hits = [author] if author else []
        else:
            hits = openalex.search_authors(query, limit=20)
        candidates = [{'id': openalex.short_id(a['id']), 'name': a.get('display_name') or 'Unknown',
            'institution': ', '.join(i['display_name'] for i in (a.get('last_known_institutions') or []))[:200] or 'Institution unavailable',
            'orcid': (a.get('orcid') or '').rsplit('/', 1)[-1], 'works_count': a.get('works_count', 0)} for a in hits]
        if os.environ.get('JEV_MODE') == 'shadow':
            from .jev_monitor import author_candidates
            target = {'name': candidates[0]['name'] if candidates and re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', orcid) else query,
                      'orcid': orcid if re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', orcid) else ''}
            author_candidates(target, candidates)
        registry.put('lookup:' + key, {'user': data['user'], 'expires': int(time.time()) + 1800, 'candidates': candidates})
        # The ingress updates the view to its waiting state before SQS dispatch completes.
        # A short delay avoids the worker racing that acknowledgement.
        time.sleep(1)
        slack_app.api(token, 'views.update', {'view_id': data['view_id'], 'view': slack_app.candidates_view(key, candidates)})


def handler(event, context):
    from botocore.exceptions import ClientError
    config = registry.credentials()
    if not config:
        raise RuntimeError('Slack credentials missing')
    for record in event['Records']:
        job = json.loads(record['body'])
        key = 'job:' + job['key'] + ':' + job['kind']
        try:
            registry.put(key, {'status': 'working', 'started_at': int(time.time()), 'kind': job['kind']}, only_new=True)
        except ClientError as exc:
            if exc.response['Error']['Code'] == 'ConditionalCheckFailedException':
                if registry.get(key).get('status') == 'complete':
                    continue
                raise RuntimeError('Previous delivery uncertain; preserve in dead-letter queue') from None
            raise
        try:
            process(job['kind'], job['data'], job['key'], config)
            registry.put(key, {'status': 'complete', 'completed_at': int(time.time()), 'kind': job['kind']})
        except Exception as exc:
            registry.put(key, {'status': 'needs_review', 'kind': job['kind'], 'error_type': type(exc).__name__,
                               'failed_at': int(time.time()), 'error': str(exc) if isinstance(exc, slack_app.SlackRejected) else type(exc).__name__})
            # Emit a metric-visible failure without logging credentials or user payloads.
            print(json.dumps({'job': job['key'], 'kind': job['kind'], 'status': 'needs_review', 'error_type': type(exc).__name__}))
            raise
