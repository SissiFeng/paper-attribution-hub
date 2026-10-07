"""Durable bounded advisory calls: local SQLite, shared DynamoDB in AWS."""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_config_lock = threading.Lock()
_refreshed = 0.0


def cloud_config():
    global _refreshed
    with _config_lock:
        if time.monotonic()-_refreshed < 60:
            return
        from . import registry
        os.environ.pop('TYPESAFE_API_KEY', None)
        registry.configure_jev()
        _refreshed = time.monotonic()


def limit():
    return max(0, min(int(os.environ.get('JEV_DAILY_CALL_LIMIT', '20')), 200))


def reusable(value):
    if not value:
        return False
    if value.get('status') == 'ok':
        return True
    return time.time() < value.get('retry_after', value.get('updated_at', 0)+86400)


def waiting(base, status):
    now = int(time.time())
    return {**base, 'status': status, 'updated_at': now,
            'retry_after': (now//86400+1)*86400 if status == 'daily_limit_reached' else now+86400}


class SQLiteJournal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,payload TEXT NOT NULL,attempted_at INTEGER)')

    @contextlib.contextmanager
    def connection(self):
        with contextlib.closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            yield db

    def claim(self, key, base):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM decisions WHERE id=?', (key,)).fetchone()
            old = json.loads(row[0]) if row else None
            if reusable(old):
                return old
            today = int(time.time())//86400*86400
            used = db.execute('SELECT count(*) FROM decisions WHERE attempted_at>=?', (today,)).fetchone()[0]
            state = waiting(base, 'started' if used < limit() else 'daily_limit_reached')
            attempted = int(time.time()) if state['status'] == 'started' else None
            db.execute('INSERT OR REPLACE INTO decisions VALUES (?,?,?)', (key, json.dumps(state), attempted))
            return None if attempted is not None else state

    def finish(self, key, value):
        with self.connection() as db:
            db.execute('UPDATE decisions SET payload=? WHERE id=?', (json.dumps(value), key))

    def get(self, key):
        with self.connection() as db:
            row = db.execute('SELECT payload FROM decisions WHERE id=?', (key,)).fetchone()
            return json.loads(row[0]) if row else {}

    def recent(self, count=20):
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM decisions ORDER BY json_extract(payload,'$.updated_at') DESC LIMIT ?", (min(count, 100),))]

    def feedback(self, key, label, reviewer):
        with self.connection() as db:
            row = db.execute('SELECT payload FROM decisions WHERE id=?', (key,)).fetchone()
            if not row:
                raise ValueError('Unknown decision')
            value = json.loads(row[0])
            value['human_feedback'] = {'label': label, 'reviewer': reviewer, 'at': int(time.time())}
            db.execute('UPDATE decisions SET payload=? WHERE id=?', (json.dumps(value), key))


class Existing(Exception):
    def __init__(self, value):
        self.value = value


class DynamoJournal:
    def claim(self, key, base):
        from . import registry
        from botocore.exceptions import ClientError
        def reserve(current):
            if reusable(current):
                raise Existing(current)
            current.clear()
            current.update(waiting(base, 'started'))
        try:
            registry.change('jev-decision:' + key, reserve)
        except Existing as old:
            return old.value
        try:
            registry.table().update_item(Key={'pk': 'jev-budget:'+str(int(time.time())//86400)},
                UpdateExpression='ADD attempts :one',
                ConditionExpression='attribute_not_exists(attempts) OR attempts < :limit',
                ExpressionAttributeValues={':one': 1, ':limit': limit()}) if limit() else self._no_budget()
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise
            result = waiting(base, 'daily_limit_reached')
            self.finish(key, result)
            return result
        return None

    @staticmethod
    def _no_budget():
        from botocore.exceptions import ClientError
        raise ClientError({'Error': {'Code': 'ConditionalCheckFailedException'}}, 'UpdateItem')

    def finish(self, key, value):
        from . import registry
        registry.put('jev-decision:'+key, value)
        def append(current):
            current['ids'] = [key] + [i for i in current.get('ids', []) if i != key][:49]
        registry.change('jev-recent', append)

    def get(self, key):
        from . import registry
        return registry.get('jev-decision:'+key)

    def recent(self, count=20):
        from . import registry
        return [self.get(i) for i in registry.get('jev-recent').get('ids', [])[:min(count, 50)]]

    def feedback(self, key, label, reviewer):
        from . import registry
        def edit(value):
            if not value:
                raise ValueError('Unknown decision')
            value['human_feedback'] = {'label': label, 'reviewer': reviewer, 'at': int(time.time())}
        registry.change('jev-decision:'+key, edit)


def journal():
    if os.environ.get('SLACK_TABLE'):
        return DynamoJournal()
    path = os.environ.get('JEV_STATE_DB') or str(Path(__file__).resolve().parents[1]/'outbox/jev-runtime.db')
    return SQLiteJournal(path)
