"""One catalogue, with independent durable delivery and recap receipts for each member."""
import json
import os

from . import notifications, registry, subscriptions
from .store import _now


class RecipientStore:
    def __init__(self, store, user):
        subscriptions.key(user)
        self.store, self.user, self.db = store, user, store.db

    def commit(self):
        self.store.commit()

    def meta(self, key):
        return self.store.meta('recipient:' + self.user + ':' + key)

    def set_meta(self, key, value):
        self.store.set_meta('recipient:' + self.user + ':' + key, value)

    def pending(self, limit):
        return self.store.rows("SELECT p.id,p.data FROM papers p JOIN deliveries d ON p.id=d.paper_id WHERE d.user_id=? AND d.status='pending' ORDER BY p.id LIMIT ?", (self.user, limit))

    def posted_between(self, start, end):
        return self.store.rows("SELECT p.id,p.data FROM papers p JOIN deliveries d ON p.id=d.paper_id WHERE d.user_id=? AND d.status='posted' AND d.posted_at>=? AND d.posted_at<? ORDER BY d.posted_at,p.id", (self.user, start, end))

    def rows(self, sql, args=()):
        return self.store.rows(sql, args)

    def set_status(self, row_id, status):
        self.db.execute('UPDATE deliveries SET status=? WHERE paper_id=? AND user_id=?', (status, row_id, self.user))
        self.commit()

    def mark_posted(self, row_id):
        self.db.execute("UPDATE deliveries SET status='posted',posted_at=? WHERE paper_id=? AND user_id=?", (_now(), row_id, self.user))
        self.commit()

    def mark_notified(self, row_id, channel, ts):
        self.db.execute('UPDATE deliveries SET channel=?,ts=? WHERE paper_id=? AND user_id=?', (channel, ts, row_id, self.user))
        self.mark_posted(row_id)


def initialize(store, members, owner):
    if store.meta('fanout_initialized'):
        return
    legacy = json.loads(store.meta('weekly_digest') or '{}')
    if legacy.get('status') == 'sending':
        raise ValueError('Reconcile the legacy digest before enabling multiple recipients')
    operator = next((m for m in members if m['user_id'] == owner), None)
    if operator:
        # Existing deliveries belong to the original operator alone, including uncertain sends.
        store.db.execute("INSERT OR IGNORE INTO deliveries(paper_id,user_id,channel,status,first_seen,posted_at,ts) SELECT p.id,?,?,p.status,p.first_seen,p.posted_at,r.ts FROM papers p LEFT JOIN notification_receipts r ON p.id=r.paper_id WHERE p.status IN ('pending','sending','posted')", (owner, operator.get('channel_id', '')))
        for name in ('weekly_recap', 'weekly_digest'):
            if store.meta(name):
                RecipientStore(store, owner).set_meta(name, store.meta(name))
    elif store.counts().get('sending') or store.counts().get('posted'):
        raise ValueError('Original operator is required to preserve existing delivery receipts')
    store.db.execute("UPDATE papers SET status='available' WHERE status IN ('pending','sending')")
    store.set_meta('fanout_initialized', _now())
    store.commit()


def send_all(store, *, now=None, members=None, owner=None, refresh=True):
    if members is None:
        owner = registry.get('settings').get('owner_id')
        if owner:
            subscriptions.request(owner)
        members = subscriptions.all_members()
    initialize(store, members, owner)
    for member in members:
        subscriptions.key(member['user_id'])
        # First-use time is the history boundary. Paused subscriptions retain their own backlog.
        store.db.execute("INSERT OR IGNORE INTO deliveries(paper_id,user_id,channel,status,first_seen) SELECT id,?,?,'pending',first_seen FROM papers WHERE status IN ('available','pending') AND first_seen>=?", (member['user_id'], member.get('channel_id', ''), member['since']))
    store.db.execute("UPDATE papers SET status='available' WHERE status='pending'")
    store.commit()
    errors, budget = [], 200
    cursor = store.meta('fanout_cursor') or ''
    members = sorted(members, key=lambda m: (m['user_id'] <= cursor, m['user_id']))
    previous_channel = os.environ.get('SLACK_CHANNEL_ID')
    unsynced = {i for i, _ in store.unsynced()}
    try:
        for member in members:
            user = member['user_id']
            # A pause while the collector is running takes effect before this recipient's batch.
            current = registry.get(subscriptions.key(user)) if refresh else member
            if not current.get('enabled'):
                continue
            if not current.get('channel_id', '').startswith('D'):
                errors.append('subscriber: private connection pending for ' + user)
                continue
            os.environ['SLACK_CHANNEL_ID'] = current['channel_id']
            recipient = RecipientStore(store, user)
            queue = [(i, p) for i, p in recipient.pending(100000) if i not in unsynced][:min(20, budget)]
            # A saved recap may continue even when this recipient has no new paper cards.
            errors.extend('subscriber ' + user + ': ' + e for e in notifications.send(recipient, queue, unsynced, now=now))
            budget -= len(queue)
            store.set_meta('fanout_cursor', user)
            store.commit()
            if budget <= 0:
                break
    finally:
        if previous_channel is None:
            os.environ.pop('SLACK_CHANNEL_ID', None)
        else:
            os.environ['SLACK_CHANNEL_ID'] = previous_channel
    active = [m['user_id'] for m in members if m.get('enabled')]
    counts = dict(store.db.execute('SELECT status,COUNT(*) FROM deliveries GROUP BY status'))
    oldest = None
    if active:
        placeholders = ','.join('?' for _ in active)
        oldest = store.db.execute(f"SELECT min(first_seen) FROM deliveries WHERE status='pending' AND user_id IN ({placeholders})", active).fetchone()[0]
    if counts.get('sending'):
        errors.append('subscriber: uncertain delivery requires recipient-specific reconciliation')
    store.set_meta('fanout_summary', json.dumps({'subscribers': len(members), 'active_subscribers': len(active),
                   'delivery_counts': counts, 'oldest_pending': oldest}))
    store.commit()
    return errors
