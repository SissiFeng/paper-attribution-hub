"""Explicit synthetic AWS canary: private S3, rolled-back PAS writes, no messages."""
from __future__ import annotations

import contextlib
import json
import uuid
from email.message import EmailMessage


def verify(store_class, path, s3, bucket, prefix):
    from app.db import SessionLocal
    from app.models import Paper as PasPaper
    from . import mailbox_state, pas, registry, scholar_graph, slack_app
    from .authors import Author
    from .models import Paper
    from .scholar_email import SENDER
    from .store import Store

    if not prefix.startswith('author-monitor/verification/'):
        raise ValueError('Synthetic canary requires a verification-only S3 prefix')
    suffix = uuid.uuid4().hex
    name = 'PAS Synthetic Author ' + suffix
    title = 'SYNTHETIC PAS reliability canary ' + suffix
    config = {'provider': 'graph', 'tenant_id': str(uuid.uuid4()), 'client_id': str(uuid.uuid4()),
              'client_secret': 'synthetic-unused', 'mailbox': 'synthetic@example.invalid',
              'folder_id': 'synthetic', 'folder': 'synthetic', 'verified_at': '2026-10-16T00:00:00Z'}
    authors = [Author(name)]

    def message(author):
        msg = EmailMessage()
        msg['From'], msg['Subject'] = SENDER, author + ' - new articles'
        msg.set_content(f'<h3><a class="gse_alrt_title" href="https://example.invalid/paper">{title}</a></h3><p>{name} - Synthetic venue, 2026</p>', subtype='html')
        return msg.as_bytes()

    bodies = {'good': message(name), 'bad': message('Unmapped synthetic author')}
    values = [{'id': key, 'from': {'emailAddress': {'address': SENDER}},
               'subject': (name if key == 'good' else 'Unmapped synthetic author') + ' - new articles',
               'receivedDateTime': '2026-10-16T00:00:00Z'} for key in bodies]
    original = scholar_graph.request
    def simulated_graph(url, **kwargs):
        if url.endswith('/$value'):
            return bodies[url.split('/')[-2]]
        return {'value': values, '@odata.deltaLink': scholar_graph.delta_url(config) + '?synthetic=1'}
    scholar_graph.request = simulated_graph
    try:
        with contextlib.closing(store_class(path)) as store:
            papers, cursor = scholar_graph.fetch_pending(store, authors, config, token='synthetic-unused')
            assert len(papers) == 1 and mailbox_state.summary(store)['mail_quarantined'] == 1
            row = store.insert(papers[0], 'pending')
            stable_id = store.ingestion_id(row)
            mailbox_state.acknowledge(store, json.loads(cursor[1])['ready_message_ids'])
            store.commit()
            values.clear()
            assert not scholar_graph.fetch_pending(store, authors, config, token='synthetic-unused')[0]
            digest = store.db.execute("SELECT content_hash FROM mail_messages WHERE status='processed'").fetchone()[0]
            assert s3.get_object(Bucket=bucket, Key=f'{prefix}/mail-raw/{digest}.eml')['Body'].read() == bodies['good']
    finally:
        scholar_graph.request = original

    copy = path.parent / 'downloaded-canary.db'
    s3.download_file(bucket, f'{prefix}/state.db', str(copy))
    with contextlib.closing(Store(copy)) as restored:
        assert mailbox_state.summary(restored)['mail_counts'] == {'processed': 1, 'quarantined': 1}
        assert restored.ingestion_id(row) == stable_id
    with SessionLocal() as session:
        try:
            first = pas.ingest_session(session, papers[0], 'main', existing_id=stable_id)
            enriched = Paper(title, authors=[name], doi='10.99999/pas-canary-' + suffix)
            second = pas.ingest_session(session, enriched, 'main', existing_id=first)
            assert first == second and session.get(PasPaper, first).doi == enriched.doi
        finally:
            session.rollback()
    with SessionLocal() as session:
        assert session.get(PasPaper, first) is None
    credentials = registry.credentials()
    if not credentials:
        raise ValueError('Slack credentials missing for read-only connectivity test')
    slack_app.api(credentials['bot_token'], 'auth.test', {})
    report = {'synthetic': True, 'graph_live_test': False, 's3_mail_roundtrip': True,
              's3_checkpoint_restore': True, 'poison_mail_isolated': True,
              'replay_deduplicated': True, 'rds_stable_id': True, 'rds_rolled_back': True,
              'slack_auth_ok': True, 'slack_messages_sent': 0, 'schedule_enabled': False}
    s3.put_object(Bucket=bucket, Key=f'{prefix}/result.json', Body=json.dumps(report).encode(), ServerSideEncryption='AES256')
    print(json.dumps(report))
    return 0
