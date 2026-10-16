"""Durable, per-message inbox. Raw mail is private and separate from checkpoints.

Capture precedes delta advancement. Parsing precedes the atomic acknowledgement
with catalogue writes, so neither a bad neighbour nor a worker restart loses mail.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import email
import hashlib
import json
import time

from .models import Paper
from .scholar_email import MailboxError, parse_message
from .store import _now

SCHEMA = """
CREATE TABLE IF NOT EXISTS mail_messages (
  id TEXT PRIMARY KEY, mailbox_key TEXT NOT NULL, message_id TEXT NOT NULL,
  received_at TEXT, metadata TEXT NOT NULL, content_hash TEXT,
  status TEXT NOT NULL, captured_at TEXT NOT NULL, processed_at TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
  error TEXT, author TEXT, paper_count INTEGER NOT NULL DEFAULT 0, parsed TEXT
);
CREATE INDEX IF NOT EXISTS ix_mail_status ON mail_messages(mailbox_key,status,retry_at);
"""


def identity(mailbox_key, message_id):
    return hashlib.sha256((mailbox_key + '\n' + message_id).encode()).hexdigest()


def received_at(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(dt.timezone.utc).isoformat(timespec='seconds')
    except (ValueError, TypeError):
        raise MailboxError('Invalid email arrival timestamp') from None


def capture(store, mailbox_key, item, *, raw=None, error=None, retry_after=900):
    key = identity(mailbox_key, item['id'])
    # S3/file write must finish before its durable ledger entry and delta cursor.
    digest = store.archive_mail(raw) if raw is not None else None
    try:
        arrival = received_at(item.get('receivedDateTime'))
    except MailboxError:
        arrival = None  # Parsing quarantines missing arrival when a history boundary is set.
    store.db.execute('''INSERT INTO mail_messages
        (id,mailbox_key,message_id,received_at,metadata,content_hash,status,captured_at,error,retry_at)
        VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        content_hash=excluded.content_hash,status=excluded.status,error=excluded.error,
        retry_at=excluded.retry_at''',
        (key, mailbox_key, item['id'], arrival, json.dumps(item), digest,
         'captured' if digest else 'fetch_retry', _now(), error,
         time.time() + retry_after if error else 0))
    return key


def parse_pending(store, mailbox_key, authors, config, *, now=None):
    now = time.time() if now is None else now
    papers, ready = [], []
    rows = store.db.execute('''SELECT id,content_hash,received_at,metadata,parsed,status
        FROM mail_messages WHERE mailbox_key=? AND
        (status IN ('captured','ready') OR status='quarantined' AND retry_at<=?)
        ORDER BY CASE status WHEN 'quarantined' THEN 1 ELSE 0 END,retry_at,id LIMIT 100''',
        (mailbox_key, now)).fetchall()
    for key, digest, arrival, metadata, parsed, status in rows:
        if status == 'ready':
            papers.extend(Paper(**p) for p in json.loads(parsed))
            ready.append(key)
            continue
        try:
            raw = store.read_mail(digest)
            msg = email.message_from_bytes(raw)
            from email.utils import parseaddr
            from .scholar_email import SENDER
            if parseaddr(msg.get('From', ''))[1].lower() != SENDER:
                raise MailboxError('Microsoft metadata and Scholar sender disagree')
            found = parse_message(msg, authors, config.get('author_aliases'))
            # Never claim a historical-boundary decision without a real arrival time.
            if found and config.get('notify_after') and not arrival:
                raise MailboxError('Email arrival timestamp is required for the notification boundary')
            from .scholar_email import alert_author
            who = alert_author(json.loads(metadata).get('subject', ''), authors, config.get('author_aliases'))
            if found and any(p.tracked_authors != [who] for p in found):
                raise MailboxError('Microsoft metadata and Scholar message disagree')
            for paper in found:
                paper.alert_received_at = arrival
        except (MailboxError, OSError, ValueError, LookupError) as exc:
            # Keep mail and a safe reason; retry after the operator fixes mapping/layout.
            reason = str(exc) if isinstance(exc, MailboxError) else type(exc).__name__
            store.db.execute("UPDATE mail_messages SET status='quarantined',error=?,attempts=attempts+1,retry_at=? WHERE id=?",
                             (reason, now + 3600, key))
            continue
        store.db.execute('''UPDATE mail_messages SET status=?,author=?,paper_count=?,parsed=?,
            attempts=attempts+1,error=NULL,retry_at=0,processed_at=? WHERE id=?''',
            ('ready' if found else 'ignored', found[0].tracked_authors[0] if found else None,
             len(found), json.dumps([dataclasses.asdict(p) for p in found]), None if found else _now(), key))
        papers.extend(found)
        if found:
            ready.append(key)
    store.commit()
    return papers, ready


def acknowledge(store, ids):
    # Caller commits this in the same transaction as the extracted catalogue rows.
    store.db.executemany("UPDATE mail_messages SET status='processed',processed_at=?,parsed=NULL WHERE id=? AND status='ready'",
                         [(_now(), key) for key in ids])


def summary(store):
    counts = dict(store.db.execute('SELECT status,COUNT(*) FROM mail_messages GROUP BY status'))
    last = store.db.execute('SELECT max(received_at) FROM mail_messages').fetchone()[0]
    return {'mail_counts': counts, 'last_message_received_at': last,
            'mail_quarantined': counts.get('quarantined', 0),
            'mail_fetch_pending': counts.get('fetch_retry', 0),
            'mail_processing_pending': counts.get('ready', 0) + counts.get('captured', 0)}


def coverage(store, authors):
    observations = {name: {'last_received_at': arrival, 'last_processed_at': processed,
                          'publication_messages': count}
                    for name, arrival, processed, count in store.db.execute('''
                        SELECT author,max(received_at),max(processed_at),COUNT(*) FROM mail_messages
                        WHERE status='processed' AND author IS NOT NULL GROUP BY author''')}
    return [{**author, 'scholar': {**author.get('scholar', {}),
                **observations.get(author['name'], {})}} for author in authors]


def prune_processed(store, *, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(days=90)).isoformat(timespec='seconds')
    # A content hash can be shared by several deliveries of the same email.
    # Keep it until every reference was processed more than 90 days ago.
    hashes = store.db.execute('''SELECT content_hash FROM mail_messages
        WHERE content_hash IS NOT NULL GROUP BY content_hash
        HAVING min(CASE WHEN status IN ('processed','ignored') AND processed_at<? THEN 1 ELSE 0 END)=1
        LIMIT 100''', (cutoff,)).fetchall()
    for (digest,) in hashes:
        store.delete_mail(digest)
        store.db.execute('UPDATE mail_messages SET content_hash=NULL WHERE content_hash=?', (digest,))
    if hashes:
        store.commit()
    return len(hashes)
