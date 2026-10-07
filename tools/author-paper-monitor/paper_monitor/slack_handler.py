"""HTTP ingress: authenticate the raw body, acknowledge quickly, queue slow work."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse

from . import registry, slack_app, subscriptions


def response(body='', status=200, content_type='application/json'):
    return {'statusCode': status, 'headers': {'Content-Type': content_type, 'Cache-Control': 'no-store'},
            'body': json.dumps(body) if not isinstance(body, str) else body}


def verify(body, headers, secret, now=None):
    headers = {k.lower(): v for k, v in headers.items()}
    stamp = headers.get('x-slack-request-timestamp', '')
    try:
        if abs((now or time.time()) - int(stamp)) > 300:
            return False
    except ValueError:
        return False
    signed = b'v0:' + stamp.encode() + b':' + body
    expected = 'v0=' + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, headers.get('x-slack-signature', ''))


def enqueue(kind, data, key):
    registry.client('sqs').send_message(QueueUrl=os.environ['SLACK_QUEUE'],
        MessageBody=json.dumps({'kind': kind, 'data': data, 'key': key}))


def ephemeral(text):
    return response({'response_type': 'ephemeral', 'text': text})


def owner(settings, user):
    return bool(settings.get('owner_id') and settings['owner_id'] == user)


def require_owner(settings, user):
    if not owner(settings, user):
        raise ValueError('Only the connected operator can change the shared watchlist or delivery settings.')


def handle(payload, config, key):
    settings = registry.get('settings')
    team = payload.get('team_id') or (payload.get('team') or {}).get('id')
    if team != config['team_id']:
        return response('Wrong workspace', 403, 'text/plain')
    user = payload.get('user_id') or (payload.get('user') or {}).get('id')
    kind = payload.get('type', 'command')
    if kind == 'event_callback':
        event = payload.get('event', {})
        if event.get('type') == 'app_home_opened':
            user = event['user']
            subscriptions.request(user)
            enqueue('home', {'user': user, 'page': 0}, key)
        return response()
    if kind == 'command':
        command, _, arg = payload.get('text', '').strip().partition(' ')
        if command == 'login':
            if not payload.get('channel_id', '').startswith('D'):
                return ephemeral('For browser sign-in, send this command in your private conversation with AC Papers.')
            from .pas_login import confirm
            confirm(arg, user, team, payload.get('user_name'))
            return ephemeral('PAS sign-in confirmed for your Slack identity. Return to the PAS browser tab. Only confirm codes shown in a browser you are using yourself.')
        if command == 'connect':
            def bind(current):
                if current.get('owner_id') and current['owner_id'] != user:
                    raise ValueError('This bot is already connected by another operator.')
                valid = current.get('connect_expires', 0) > time.time() and hmac.compare_digest(
                    current.get('connect_hash', ''), hashlib.sha256(arg.strip().encode()).hexdigest())
                if not valid:
                    raise ValueError('Connection code expired or incorrect. Generate another with connect_slack.py.')
                current.update(owner_id=user, dm_user_id=user, channel_id='', delivery_mode='personal', enabled=False, tested_channel='', connect_hash='', connect_expires=0, connection_key=key)
            settings = registry.change('settings', bind)
            enqueue('connect_dm', {'user': user}, key)
            return ephemeral('Opening a private conversation with AC Papers for you. No messages will be sent to this channel. Follow the instructions in the bot’s direct message.')
        if command in ('home', 'authors', 'status', 'test', 'digest', 'review', 'decisions', 'start', 'pause'):
            personal = subscriptions.request(user, enabled=(command == 'start') if command in ('start', 'pause') else None)
        if command in ('home', 'authors'):
            enqueue('home', {'user': user, 'page': 0}, key)
            return ephemeral('Your author watchlist is available in the AC Papers Home tab.')
        if command == 'status':
            if not personal.get('channel_id'):
                enqueue('home', {'user': user, 'page': 0}, key)
            settings = subscriptions.view(user)
            rows = registry.authors()
            count = sum(r.get('status') == 'active' for r in rows)
            return ephemeral(f"{len(rows)} authors listed; {count} active. Notifications: {'enabled' if settings.get('enabled') else 'paused'}. "
                             f"Last successful collection: {settings.get('last_collection', 'not run yet')}. Checks every 4 hours; new-paper messages plus a Monday 12:17 UTC recap.\n" + slack_app.monitor_status(settings) + '\n' + slack_app.jev_status(settings))
        if command == 'add':
            require_owner(settings, user)
        if command == 'add':
            slack_app.api(config['bot_token'], 'views.open', {'trigger_id': payload['trigger_id'], 'view': slack_app.add_modal()}, timeout=1.6)
            return response()
        if command in ('review', 'decisions'):
            enqueue('jev_review' if command == 'review' else 'jev_decisions', {'user': user}, key)
            return ephemeral('Preparing experimental suggestions in your own private conversation.')
        if command in ('test', 'digest'):
            enqueue('preview', {'user': user}, key)
            return ephemeral('Preparing a real-paper preview in your own private conversation. It does not change automatic delivery history.')
        if command in ('start', 'pause'):
            enqueue('home', {'user': user, 'page': 0}, key)
            return ephemeral('Your private updates are enabled. Checks run every 4 hours, with a Monday recap.' if command == 'start'
                             else 'Only your updates are paused. Collection and other members’ subscriptions continue.')
        return ephemeral('AC Papers: `/papers start` · `test` · `review` · `decisions` · `pause` · `status` · `authors` · `add`\nOpen AC Papers or use `/papers start` to subscribe in your own DM. The shared watchlist is managed by its administrator.')
    if kind == 'block_actions':
        action = payload['actions'][0]
        name, value = action['action_id'], action.get('value', '')
        if name == 'read_paper':
            return response()
        if name == 'jev_feedback':
            require_owner(settings, user)
            from .jev_ledger import journal
            entry = journal().get(value)
            if entry.get('status') != 'ok':
                raise ValueError('This decision is unavailable for review.')
            slack_app.api(config['bot_token'], 'views.open', {'trigger_id': payload['trigger_id'],
                'view': slack_app.decision_feedback_modal(entry)}, timeout=1.6)
            return response()
        if name.startswith('feedback_') or name == 'paper_more':
            value = value or action.get('selected_option', {}).get('value', '')
            if len(value) != 32 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Invalid paper identifier')
            enqueue('feedback', {'paper': value, 'user': user, 'vote': name,
                                'channel': payload.get('channel', {}).get('id')}, key)
        elif name in ('home', 'home_previous', 'home_next'):
            subscriptions.request(user)
            enqueue('home', {'user': user, 'page': int(value)}, key)
        elif name in ('notifications_start', 'notifications_pause'):
            # Personal toggles always use the authenticated member, never a supplied target.
            return handle({'team_id': team, 'user_id': user,
                           'text': 'start' if name == 'notifications_start' else 'pause'}, config, key)
        elif name in ('jev_review', 'jev_decisions'):
            return handle({'team_id': team, 'user_id': user, 'text': 'review' if name == 'jev_review' else 'decisions'}, config, key)
        elif name in ('author_pause', 'author_resume'):
            require_owner(settings, user)
            def toggle_author(row):
                if not row.get('openalex_ids'):
                    raise ValueError('Verify the author identity before activation.')
                row['status'] = 'paused' if name == 'author_pause' else 'active'
            registry.change('author:' + value, toggle_author)
            enqueue('home', {'user': user, 'page': 0}, key)
        elif name == 'test':
            return handle({'team_id': team, 'user_id': user, 'text': 'test'}, config, key)
        elif name == 'add_author':
            require_owner(settings, user)
            slack_app.api(config['bot_token'], 'views.open', {'trigger_id': payload['trigger_id'], 'view': slack_app.add_modal()}, timeout=1.6)
        return response()
    if kind == 'view_submission':
        require_owner(settings, user)
        view = payload['view']
        if view['callback_id'] == 'jev_feedback':
            from .jev_ledger import journal
            from .jev_tasks import question
            ledger = journal()
            entry = ledger.get(view['private_metadata'])
            if entry.get('status') != 'ok':
                raise ValueError('This decision is unavailable for review.')
            label = view['state']['values']['label']['value']['selected_option']['value']
            criteria = question(entry['task'])['criteria']
            allowed = {str(i) for i in range(len(criteria))} if isinstance(criteria, list) else set(criteria)
            if label not in allowed:
                raise ValueError('Unknown review label.')
            ledger.feedback(view['private_metadata'], label, user)
            return response({'response_action': 'clear'})
        if view['callback_id'] == 'author_search':
            query = view['state']['values']['query']['value']['value'].strip()
            enqueue('lookup', {'user': user, 'view_id': view['id'], 'query': query}, key)
            return response({'response_action': 'update', 'view': slack_app.searching_view()})
        if view['callback_id'] == 'author_choose':
            lookup = registry.get('lookup:' + view['private_metadata'])
            chosen = view['state']['values']['author']['value']['selected_option']['value']
            if lookup.get('user') != user or lookup.get('expires', 0) < time.time():
                return response({'response_action': 'errors', 'errors': {'author': 'This lookup expired. Close and search again.'}})
            candidate = next((a for a in lookup['candidates'] if a['id'] == chosen), None)
            if not candidate:
                raise ValueError('Unknown author candidate')
            rows = registry.authors()
            existing = next((r for r in rows if chosen in r.get('openalex_ids', [])), None)
            if not existing:
                pid = 'custom_' + chosen
                registry.put('author:' + pid, {'person_id': pid, 'name': candidate['name'], 'orcid': candidate['orcid'],
                    'institution': candidate['institution'], 'openalex_ids': [chosen], 'status': 'active',
                    'confirmed_by': user, 'confirmed_at': int(time.time())}, only_new=True)
            enqueue('home', {'user': user, 'page': 0}, key)
            return response({'response_action': 'clear'})
    return response()


def handler(event, context):
    path = event.get('rawPath', '/')
    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    if method == 'GET':
        if path == '/health':
            return response({'status': 'ok', 'service': 'ac-papers-slack'})
        if path == '/manifest.json':
            return response(slack_app.manifest(os.environ['PUBLIC_URL']))
        from .setup_page import HTML
        return response(HTML, content_type='text/html; charset=utf-8')
    if method != 'POST' or path != '/slack':
        return response('Not found', 404, 'text/plain')
    config = registry.credentials()
    if not config:
        return response('Slack App credentials have not been configured', 503, 'text/plain')
    body = event.get('body') or ''
    raw = base64.b64decode(body) if event.get('isBase64Encoded') else body.encode()
    if not verify(raw, event.get('headers', {}), config['signing_secret']):
        return response('Invalid signature', 401, 'text/plain')
    try:
        headers = {k.lower(): v for k, v in event.get('headers', {}).items()}
        if 'application/json' in headers.get('content-type', ''):
            payload = json.loads(raw)
        else:
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
            payload = json.loads(form['payload']) if 'payload' in form else form
        if payload.get('type') == 'url_verification':
            return response({'challenge': payload['challenge']})
        # Include the signed timestamp: a retry has the same key, a new command does not.
        key = hashlib.sha256(headers['x-slack-request-timestamp'].encode() + b':' + raw).hexdigest()
        if payload.get('type') == 'event_callback' and payload.get('event_id'):
            key = 'event:' + payload['event_id']
        # Synchronous state mutations need replay protection too. Retain the original ack.
        cached = registry.get('ack:' + key)
        if cached:
            return cached
        result = handle(payload, config, key)
        registry.put('ack:' + key, result)
        return result
    except (ValueError, KeyError, TimeoutError) as exc:
        # UI errors contain only our controlled messages, not Slack request content.
        message = str(exc) if isinstance(exc, ValueError) else 'Request could not complete. Please try again.'
        return ephemeral(message)
