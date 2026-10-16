import copy
import json
import urllib.error
from pathlib import Path

import pytest
from sqlalchemy import func, select

from paper_monitor import health, mailbox_state, notifications, pas, scholar_email, scholar_graph, slack_app
from paper_monitor.models import Paper
from paper_monitor.store import Store
from test_freshness import fake_registry
from test_pas_integration import session
from test_scholar_graph import CONFIG, item
from test_scholar_mailbox import AUTHORS, FX, message


def test_metadata_paragraph_and_nested_title_are_complete():
    html = FX.read_text().replace('<div style="color:#006621;line-height:18px">', '<p>').replace('</div>', '</p>')
    papers = scholar_email.parse_message(message(body=html), AUTHORS)
    assert len(papers) == 2
    assert papers[0].title == 'Brand new preprint on molecular graphs'


def test_missing_second_metadata_never_returns_partial_success():
    html = FX.read_text().replace('A von Lilienfeld, D Zoe - Journal of the American Chemical Society, 2026', '')
    with pytest.raises(scholar_email.MailboxError, match='metadata'):
        scholar_email.parse_message(message(body=html), AUTHORS)


def mock_mail(monkeypatch, values, bodies):
    url = scholar_graph.delta_url(CONFIG)
    monkeypatch.setattr(scholar_graph, 'access_token', lambda _: 'token')
    def request(link, **kwargs):
        if link.endswith('/$value'):
            key = link.split('/')[-2]
            body = bodies[key]
            if isinstance(body, Exception):
                raise body
            return body.as_bytes()
        return {'value': values, '@odata.deltaLink': url + '?delta=1'}
    monkeypatch.setattr(scholar_graph, 'request', request)


def test_poison_mail_is_retained_and_neighbours_survive_restart(tmp_path, monkeypatch):
    values = [item('good'), item('bad', 'Unknown Author - new articles')]
    mock_mail(monkeypatch, values, {'good': message(), 'bad': message(subject='Unknown Author - new articles')})
    path = tmp_path / 'state.db'
    store = Store(path)
    papers, cursor = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    report = json.loads(cursor[1])
    assert len(papers) == 2 and report['poll_ok']
    assert mailbox_state.summary(store)['mail_quarantined'] == 1
    assert store.meta(cursor[0])  # Raw mail is durable even before catalogue insertion.
    store.close()
    store = Store(path)
    # The cursor need not replay old emails: ready mail is replayed from private storage.
    mock_mail(monkeypatch, [], {})
    replay, again = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert [p.title for p in replay] == [p.title for p in papers]
    for paper in replay:
        store.insert(paper, 'pending')
    mailbox_state.acknowledge(store, json.loads(again[1])['ready_message_ids'])
    store.commit()
    assert not scholar_graph.fetch_pending(store, AUTHORS, CONFIG)[0]
    # A corrected alias can replay the retained original without another Graph fetch.
    store.db.execute("UPDATE mail_messages SET retry_at=0 WHERE status='quarantined'")
    fixed = {**CONFIG, 'author_aliases': {'Unknown Author': AUTHORS[0].name}}
    assert len(scholar_graph.fetch_pending(store, AUTHORS, fixed)[0]) == 2
    store.close()


def test_missing_message_does_not_block_successful_mail(tmp_path, monkeypatch):
    mock_mail(monkeypatch, [item('gone'), item('good')],
              {'gone': scholar_graph.GraphError(404), 'good': message()})
    store = Store(tmp_path / 's.db')
    papers, cursor = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert len(papers) == 2 and json.loads(cursor[1])['poll_ok']
    assert mailbox_state.summary(store)['mail_fetch_pending'] == 1
    store.close()


def test_archive_failure_never_advances_delta(tmp_path, monkeypatch):
    mock_mail(monkeypatch, [item('good')], {'good': message()})
    store = Store(tmp_path / 's.db')
    monkeypatch.setattr(store, 'archive_mail', lambda _: (_ for _ in ()).throw(OSError('storage down')))
    with pytest.raises(OSError):
        scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert not store.db.execute("SELECT 1 FROM metadata WHERE key LIKE 'scholar_graph_cursor:%'").fetchone()
    store.close()


def test_doi_enrichment_reuses_pas_id_and_updates_metadata(session, monkeypatch, tmp_path):
    from app.config import settings
    from app.models import Paper as PasPaper
    monkeypatch.setattr(settings, 'sdl_stage1_only', False)
    monkeypatch.setattr(settings, 'zotero_source_only', False)
    store = Store(tmp_path / 's.db')
    first = Paper('Distinctive publication without an initial DOI', authors=['Ada Researcher'])
    row = store.insert(first, 'pending')
    original = pas.ingest_session(session, first, 'main', existing_id=store.ingestion_id(row))
    session.commit()
    store.mark_synced(row, original)
    update = Paper(first.title, authors=first.authors, doi='10.1234/late-doi', abstract='Later abstract')
    store.add_ids(row, update)
    assert store.ingestion_id(row) == original and len(store.unsynced()) == 1
    receipt = pas.ingest_session(session, store.unsynced()[0][1], 'main', existing_id=store.ingestion_id(row))
    session.commit()
    assert receipt == original
    assert session.scalar(select(func.count(PasPaper.id))) == 1
    assert session.get(PasPaper, original).doi == update.doi
    assert session.get(PasPaper, original).abstract == update.abstract
    store.mark_synced(row, receipt)
    assert not store.unsynced()
    store.close()


def test_preexisting_corpus_match_requires_author_and_nonconflicting_doi(session, monkeypatch):
    from app.config import settings
    from app.models import Paper as PasPaper
    from app.services.ingestion_service import _attach_authors
    monkeypatch.setattr(settings, 'sdl_stage1_only', False)
    monkeypatch.setattr(settings, 'zotero_source_only', False)
    legacy = PasPaper(id='legacy-wiki-id', title='A very distinctive existing study', provenance='csv')
    session.add(legacy)
    session.flush()
    _attach_authors(session, legacy, ['Ada Researcher'], [])
    session.commit()
    p = Paper(legacy.title, authors=['Ada Researcher'], doi='10.1234/enriched')
    assert pas.ingest_session(session, p, 'main') == 'legacy-wiki-id'
    assert pas.ingest_session(session, Paper(p.title, authors=['Different Person']), 'main') != legacy.id


def test_watchdog_429_can_retry_but_timeout_still_needs_reconciliation(monkeypatch):
    data = fake_registry(monkeypatch)
    calls = []
    def limited(*args):
        calls.append(args)
        raise urllib.error.HTTPError('https://slack.com', 429, 'limited', {'Retry-After': '75'}, None)
    monkeypatch.setattr(slack_app, 'api', limited)
    with pytest.raises(urllib.error.HTTPError):
        health.notify({'test': 'test'}, now=100)
    assert data['monitor-incident']['status'] == 'retryable'
    assert data['monitor-incident']['retry_after'] == 175
    assert not health.notify({'test': 'test'}, now=174)['sent']
    monkeypatch.setattr(slack_app, 'api', lambda *_: {'ts': '1'})
    assert health.notify({'test': 'test'}, now=175)['sent']


def test_successful_recipient_send_has_two_durable_checkpoints(tmp_path, monkeypatch):
    from paper_monitor.fanout import RecipientStore
    class CountStore(Store):
        commits = 0
        def commit(self):
            super().commit()
            self.commits += 1
    store = CountStore(tmp_path / 's.db')
    row = store.insert(Paper('Test'), 'available')
    store.db.execute("INSERT INTO deliveries VALUES (?, 'U1', 'D1', 'pending', '2026-10-16', NULL, NULL)", (row,))
    recipient = RecipientStore(store, 'U1')
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'test')
    monkeypatch.setattr(slack_app, 'api', lambda *_: {'ts': '1'})
    monkeypatch.setattr(notifications.time, 'sleep', lambda _: None)
    before = store.commits
    assert not notifications._post(recipient, {'channel': 'D1'},
        lambda: recipient.set_status(row, 'sending'), lambda ts: recipient.mark_notified(row, 'D1', ts),
        lambda: recipient.set_status(row, 'pending'), callbacks_commit=True)
    assert store.commits - before == 2
    store.close()
