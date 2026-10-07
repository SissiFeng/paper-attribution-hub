"""Exercise the deployed fanout with two simulated identities, only in the owner's DM.

No synthetic subscribers or papers are written to production. An isolated S3
checkpoint tests durable per-recipient receipts and restart deduplication.
"""
import json
import os
from pathlib import Path
import tempfile

import boto3
from sqlalchemy import text
from app.db import engine, SessionLocal
from app.models import Paper as PasPaper
from paper_monitor import fanout, registry, slack_app
from paper_monitor.store import Store

s3 = boto3.client('s3')
bucket = os.environ['MONITOR_BUCKET']
prefix = 'author-monitor/acceptance/' + os.environ['FRESHNESS_TEST_ID']
production = 'author-monitor/production/state.db'
settings = registry.get('settings')
assert settings['owner_id'] == 'U07K96PT5CL'
assert settings['channel_id'] == settings['tested_channel'] == 'D0C6GC4H04F'
os.environ['SLACK_BOT_TOKEN'] = registry.credentials()['bot_token']
members = [dict(user_id=user, channel_id=settings['channel_id'], enabled=True, since='2000-01-01')
           for user in ('UTEST1', 'UTEST2')]
with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as lock:
    assert lock.scalar(text('SELECT pg_try_advisory_lock(741930, 1)')), 'Collector is running'
    before = s3.head_object(Bucket=bucket, Key=production)['VersionId']
    assert not s3.list_objects_v2(Bucket=bucket, Prefix=prefix + '/', MaxKeys=1).get('Contents'), 'Test ID already used'
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
        paper.title = 'TEST · Two-subscriber routing · ' + paper.title

        class Checkpoint(Store):
            def commit(self):
                lock.execute(text('SELECT 1'))
                super().commit()
                s3.upload_file(str(root / 'test.db'), bucket, prefix + '/state.db')

        state = Checkpoint(root / 'test.db')
        fanout.initialize(state, members, 'UTEST1')
        row_id = state.insert(paper, 'pending')
        state.mark_synced(row_id, pas_id)
        assert not fanout.send_all(state, members=members, owner='UTEST1', refresh=False)
        receipts = [dict(zip(('user_id', 'channel', 'ts', 'status'), row)) for row in
                    state.db.execute('SELECT user_id,channel,ts,status FROM deliveries ORDER BY user_id')]
        assert len(receipts) == 2 and all(r['ts'] and r['status'] == 'posted' for r in receipts)
        assert len({r['ts'] for r in receipts}) == 2
        state.close()
        s3.download_file(bucket, prefix + '/state.db', str(root / 'test.db'))
        state = Checkpoint(root / 'test.db')

        def forbid(*args, **kwargs):
            raise AssertionError('Restart tried to send a duplicate')

        slack_app.api = forbid
        assert not fanout.send_all(state, members=members, owner='UTEST1', refresh=False)
        state.close()
    assert s3.head_object(Bucket=bucket, Key=production)['VersionId'] == before
    result = dict(status='passed', mode='subscribers', simulated_members=2,
                  real_human_recipients=1, receipts=receipts, pas_id=pas_id,
                  labelled_test_messages=2, restart_posts=0, production_state_unchanged=True,
                  production_version=before, new_pas_records_in_this_probe=0,
                  bundle_sha256=os.environ['MONITOR_SHA256'])
    s3.put_object(Bucket=bucket, Key=prefix + '/result.json', Body=json.dumps(result).encode())
    print(json.dumps(result))
    lock.execute(text('SELECT pg_advisory_unlock(741930, 1)'))
