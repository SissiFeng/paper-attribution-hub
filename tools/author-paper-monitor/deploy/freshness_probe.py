"""Cloud acceptance: one labelled DM, isolated checkpoint, real existing PAS record.

Executed by verify_freshness.py inside the deployed ECS image and monitor bundle.
It never inserts a synthetic paper into PAS or edits the production monitor state.
"""
import json
import datetime as dt
import os
from pathlib import Path
import tempfile

import boto3
from sqlalchemy import text
from app.db import engine, SessionLocal
from app.models import Paper as PasPaper
from paper_monitor import notifications, registry, slack_app
from paper_monitor.store import Store

s3 = boto3.client('s3')
bucket = os.environ['MONITOR_BUCKET']
prefix = 'author-monitor/acceptance/' + os.environ['FRESHNESS_TEST_ID']
production = 'author-monitor/production/state.db'
weekly = os.environ.get('FRESHNESS_TEST_MODE') == 'weekly'
settings = registry.get('settings')
assert settings['enabled'] and settings['channel_id'].startswith('D')
assert settings['tested_channel'] == settings['channel_id']
config = registry.credentials()
os.environ.update(SLACK_BOT_TOKEN=config['bot_token'], SLACK_CHANNEL_ID=settings['channel_id'])

with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as lock:
    assert lock.scalar(text('SELECT pg_try_advisory_lock(741930, 1)')), 'Collector is still running'
    before = s3.head_object(Bucket=bucket, Key=production)['VersionId']
    existing = s3.list_objects_v2(Bucket=bucket, Prefix=prefix + '/', MaxKeys=1)
    assert not existing.get('Contents'), 'Test ID already used; inspect its checkpoint instead of replaying'
    s3.put_object(Bucket=bucket, Key=prefix + '/started.json', Body=b'{}')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        s3.download_file(bucket, production, str(root / 'source.db'))
        source = Store(root / 'source.db')
        row_id, paper = source.rows('SELECT p.id,p.data FROM papers p JOIN ingestion i ON p.id=i.paper_id WHERE i.pas_id IS NOT NULL ORDER BY p.id LIMIT 1')[0]
        pas_id = source.db.execute('SELECT pas_id FROM ingestion WHERE paper_id=?', (row_id,)).fetchone()[0]
        with SessionLocal() as db:
            stored = db.get(PasPaper, pas_id)
            assert stored and stored.title == paper.title
        source.close()
        paper.title = 'TEST · Delivery check · ' + paper.title

        class Checkpoint(Store):
            def commit(self):
                lock.execute(text('SELECT 1'))
                super().commit()
                s3.upload_file(str(root / 'test.db'), bucket, prefix + '/state.db')

        state = Checkpoint(root / 'test.db')
        test_row = state.insert(paper, 'posted' if weekly else 'pending')
        state.mark_synced(test_row, pas_id)
        original_api = slack_app.api
        if weekly:
            now = dt.datetime.now(dt.timezone.utc)
            previous_friday = now - dt.timedelta(days=now.weekday()+3)
            state.db.execute('UPDATE papers SET posted_at=? WHERE id=?', (previous_friday.isoformat(), test_row))
            state.commit()

            def labelled(token, method, payload):
                payload = {**payload, 'text': 'TEST · ' + payload['text'],
                    'blocks': [slack_app.section('*TEST · Weekly recap delivery check*\nIsolated sample; no production publication dates were changed.')] + payload['blocks']}
                return original_api(token, method, payload)

            slack_app.api = labelled
        errors = notifications.send(state, state.pending(20), set())
        assert not errors, errors
        if weekly:
            recap = json.loads(state.meta('weekly_recap'))
            assert recap['status'] == 'complete' and recap['page_receipts']['0']
            receipt = (recap['channel'], recap['ts'])
        else:
            receipt = state.db.execute('SELECT channel,ts FROM notification_receipts WHERE paper_id=?', (test_row,)).fetchone()
        assert receipt and state.counts() == {'posted': 1}
        state.close()
        s3.download_file(bucket, prefix + '/state.db', str(root / 'test.db'))
        state = Checkpoint(root / 'test.db')

        def forbid(*args, **kwargs):
            raise AssertionError('A restarted worker tried to send the same test again')

        slack_app.api = forbid
        assert not notifications.send(state, state.pending(20), set())
        slack_app.api = original_api
        state.close()
    after = s3.head_object(Bucket=bucket, Key=production)['VersionId']
    assert after == before, 'Production state changed during isolated acceptance'
    result = {'status': 'passed', 'pas_id': pas_id, 'real_existing_paper': True,
              'new_pas_records_in_this_probe': 0, 'labelled_test_messages': 2 if weekly else 1,
              'mode': 'weekly' if weekly else 'immediate',
              'thread_ts': recap['page_receipts']['0'] if weekly else None,
              'channel': receipt[0], 'ts': receipt[1], 'restart_posts': 0,
              'production_state_unchanged': True, 'production_version': before,
              'bundle_sha256': os.environ['MONITOR_SHA256']}
    s3.put_object(Bucket=bucket, Key=prefix + '/result.json', Body=json.dumps(result).encode())
    print(json.dumps(result))
    lock.execute(text('SELECT pg_advisory_unlock(741930, 1)'))
