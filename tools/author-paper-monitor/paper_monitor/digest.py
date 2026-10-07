"""Weekly delivery with durable parent/thread receipts and explicit uncertainty."""
from __future__ import annotations

import datetime
import json
import os
import time
import urllib.error

from . import slack_app


def send(store, queue, unsynced, *, now=None):
    if not os.environ.get('SLACK_CHANNEL_ID', '').startswith('D'):
        return ['Personal mode requires a direct-message destination; refusing a group channel']
    now = now or datetime.datetime.now(datetime.timezone.utc)
    week = (now.date() - datetime.timedelta(days=now.weekday())).isoformat()
    state = json.loads(store.meta('weekly_digest') or '{}')
    errors = []
    if state.get('status') == 'sending':
        return ['Weekly digest parent delivery is uncertain; operator reconciliation required']
    # A previous batch finishes before opening a new week's parent.
    ids = state.get('ids', [])
    remaining = [i for i, _ in store.pending(100000) if i in ids]
    if state.get('week') != week and not remaining:
        if now.weekday() != 0:
            return []
        queue = [(i, p) for i, p in store.pending(100000) if i not in unsynced]
        if not queue:
            return []
        state = {'week': week, 'status': 'sending', 'ids': [i for i, _ in queue],
                 'channel': os.environ['SLACK_CHANNEL_ID']}
        store.set_meta('weekly_digest', json.dumps(state))
        store.commit()
        try:
            result = slack_app.api(os.environ['SLACK_BOT_TOKEN'], 'chat.postMessage',
                {'channel': state['channel'], **slack_app.digest([p for _, p in queue])})
            if not result.get('ts'):
                raise ValueError('Missing Slack timestamp')
        except slack_app.SlackRejected as exc:
            store.set_meta('weekly_digest', '{}')
            store.commit()
            return [str(exc)]
        except (OSError, ValueError):
            return ['Weekly digest parent delivery uncertain; inspect Slack before retrying']
        state.update(status='posted', ts=result['ts'])
        store.set_meta('weekly_digest', json.dumps(state))
        store.commit()
        ids = state['ids']
    if not state.get('ts'):
        return []
    # This digest has a frozen list; later discoveries wait for next Monday.
    batch = [(i, p) for i, p in store.pending(100000) if i in ids and i not in unsynced][:20]
    for row_id, p in batch:
        receipt = store.db.execute('SELECT pas_id FROM ingestion WHERE paper_id=?', (row_id,)).fetchone()
        store.set_status(row_id, 'sending')
        try:
            result = slack_app.api(os.environ['SLACK_BOT_TOKEN'], 'chat.postMessage',
                {'channel': state['channel'], 'thread_ts': state['ts'], **slack_app.card(p, pas_id=receipt[0] if receipt else None)})
            if not result.get('ts'):
                raise ValueError('Missing Slack timestamp')
        except (slack_app.SlackRejected, urllib.error.HTTPError) as exc:
            if isinstance(exc, slack_app.SlackRejected) or exc.code < 500:
                store.set_status(row_id, 'pending')
            errors.append('Slack rejected/failed thread delivery; inspect logs before retry')
            break
        except (OSError, ValueError):
            errors.append('Slack thread delivery uncertain; reconcile required')
            break
        store.mark_posted(row_id)
        time.sleep(1.1)
    return errors
