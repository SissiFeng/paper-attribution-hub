import datetime
import sqlite3
from email.utils import format_datetime


from paper_monitor import arxiv, authors, http, pas, slack
from paper_monitor.cli import dedup_batch, main
from paper_monitor.models import Paper, normalize_title
from paper_monitor.store import Store
from test_monitor import new_work




def test_distinct_dois_and_generic_titles_are_not_merged(tmp_path):
    for title in ("Editorial", "Long specific title about catalysis"):
        a = Paper(title, doi="10.1/a", authors=["A"])
        b = Paper(title, doi="10.1/b", authors=["A"])
        assert len(dedup_batch([a, b])) == 2
        store = Store(tmp_path / (title + ".db"))
        store.insert(a, "posted")
        assert store.find(b) is None
        store.close()
    assert len(dedup_batch([Paper("Editorial", authors=["A"]), Paper("Editorial", authors=["A"])])) == 2


def test_journal_alias_survives_title_change_and_restart(tmp_path):
    store = Store(tmp_path / "s.db")
    i = store.insert(Paper("A useful scientific title", doi="10.48550/arxiv.2601.00001", authors=["A"]), "posted")
    journal = Paper("A useful scientific title", doi="10.1/journal", authors=["A"])
    assert store.find(journal) == i
    store.add_ids(i, journal)
    store.commit()
    store.close()
    store = Store(tmp_path / "s.db")
    assert store.find(Paper("Entirely changed title", doi="10.1/journal")) == i
    assert "10.1/journal" in store.rows("SELECT id,data FROM papers")[0][1].doi_aliases
    store.close()


def test_empty_baseline_next_publication_is_new(env):
    web, run, statuses, _, _, tmp = env
    web.works["results"] = []
    (tmp / "authors.csv").write_text("name,openalex_ids\nA,A5000000001\n")
    assert run() == 0
    web.works["results"] = [new_work("First real publication", "10.1/first")]
    assert run() == 0
    assert statuses()["first real publication"] == "pending"


def test_unresolved_author_aborts_before_database_creation(env):
    _, run, _, _, _, tmp = env
    (tmp / "authors.csv").write_text("name,openalex_ids\nWrong Person,\n")
    assert run() == 1
    assert not (tmp / "state.db").exists()


def test_orcid_name_mismatch_is_never_auto_accepted(monkeypatch):
    monkeypatch.setattr(authors.openalex, "author_by_orcid", lambda _: {"id": "A123", "display_name": "Adam Jackson"})
    monkeypatch.setattr(authors.openalex, "search_authors", lambda _: [])
    rows = [authors.Author("Anatole von Lilienfeld", orcid="0000-0001-5272-6530")]
    assert "MISMATCH" in authors.resolve(rows)[0]
    assert rows[0].openalex_ids == []


def test_retry_after_date_invalid_and_negative():
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
    assert 28 <= http.retry_delay(format_datetime(future), 0) <= 30
    assert http.retry_delay("not a date", 2) == 4
    assert http.retry_delay("-10", 0) == 0


def test_arxiv_paginates_and_spaces_queries(monkeypatch):
    calls, delays = [], []
    def fetch(url, params):
        calls.append(params)
        n = 100 if len(calls) == 1 else 1
        return ('<feed xmlns="http://www.w3.org/2005/Atom">' + ''.join(
            f'<entry><id>https://arxiv.org/abs/2609.{i:05}</id><published>2026-09-01</published><title>T</title></entry>'
            for i in range(n)) + '</feed>').encode()
    monkeypatch.setattr(http, "request", fetch)
    monkeypatch.setattr(arxiv.time, "sleep", delays.append)
    assert len(list(arxiv.recent_preprints({"A": "au:A", "B": "au:B"}, "2026-07-01"))) == 102
    assert [c["start"] for c in calls] == [0, 100, 0]
    assert delays == [3.1, 3.1]


def test_ambiguous_slack_delivery_requires_explicit_reconciliation(env):
    web, run, statuses, _, mp, tmp = env
    assert run() == 0
    mp.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    web.works["results"].append(new_work("Uncertain delivery", "10.1/uncertain"))
    calls = []
    def uncertain(p):
        calls.append(p)
        raise TimeoutError("after request")
    mp.setattr(slack, "post", uncertain)
    assert run() == 1
    assert statuses()["uncertain delivery"] == "sending"
    assert run() == 1 and len(calls) == 1
    i = sqlite3.connect(tmp / "state.db").execute("SELECT id FROM papers WHERE status='sending'").fetchone()[0]
    assert main(["reconcile", "--db", str(tmp / "state.db"), "--id", str(i), "--delivered"]) == 0
    assert run() == 0 and len(calls) == 1


def test_pas_retry_before_slack_and_dry_run_has_no_external_writes(env):
    web, run, statuses, _, mp, _ = env
    assert run() == 0
    mp.setenv("PAS_MONITOR_INGEST", "1")
    mp.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    web.works["results"].append(new_work("Database before notification", "10.1/pas"))
    calls = []
    def failing(p, **kwargs):
        calls.append(p)
        raise RuntimeError("DB unavailable")
    mp.setattr(pas, "ingest", failing)
    assert run("--dry-run") == 0 and not calls and not web.slack_posts
    assert run() == 1 and len(calls) == 4 and not web.slack_posts
    mp.setattr(pas, "ingest", lambda p, **kwargs: calls.append(p) or "pas_123")
    assert run() == 0 and len(calls) == 8 and len(web.slack_posts) == 1  # three baseline records also ingest
    assert run() == 0 and len(calls) == 8 and len(web.slack_posts) == 1  # three baseline records also ingest


def test_unicode_title_preserved():
    assert normalize_title("自动化实验") != normalize_title("化学论文")


def test_changed_brief_reconsiders_irrelevant(env):
    web, run, statuses, _, mp, tmp = env
    assert run() == 0
    mp.setenv("ANTHROPIC_API_KEY", "test")
    (tmp / "brief.txt").write_text("chemistry")
    web.llm = {"relevant": False, "summary": "Other topic"}
    web.works["results"].append(new_work("A biological paper", "10.1/bio"))
    assert run() == 0 and statuses()["a biological paper"] == "irrelevant"
    (tmp / "brief.txt").write_text("biology")
    web.llm = {"relevant": True, "summary": "Relevant now"}
    assert run() == 0 and statuses()["a biological paper"] == "pending"


def test_legacy_database_backfills_aliases_payload_and_pas_receipt(tmp_path):
    import json
    path = tmp_path / 'legacy.db'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE papers(id INTEGER PRIMARY KEY,doi TEXT,arxiv_id TEXT,title_key TEXT,data TEXT,status TEXT,first_seen TEXT,posted_at TEXT)')
    db.execute('INSERT INTO papers VALUES(1,?,?,?,?,?,?,NULL)', (
        '10.1/later', '2601.00001', 'original title',
        json.dumps({'title': 'Original title', 'doi': '10.48550/arxiv.2601.00001'}),
        'pending', '2026-01-01'))
    db.commit()
    db.close()
    store = Store(path)
    assert store.meta('initialized') == '1'
    assert store.find(Paper('Renamed', doi='10.1/later')) == 1
    assert store.find(Paper('Renamed again', doi='10.48550/arxiv.2601.00001')) == 1
    assert store.unsynced()[0][0] == 1
    store.close()
