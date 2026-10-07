import copy
import json
import sqlite3
import urllib.error
from pathlib import Path

import pytest

from paper_monitor import arxiv, http, openalex, scholar_email, slack
from paper_monitor.cli import dedup_batch, main
from paper_monitor.models import Paper, normalize_doi, normalize_title

FX = Path(__file__).parent / "fixtures"
OA = json.loads((FX / "openalex_works.json").read_text())
ID2NAME = {"A5000000001": "Alán Aspuru-Guzik", "A5000000002": "Anatole von Lilienfeld"}


# ---------------------------------------------------------------- parsing

def test_normalizers():
    assert normalize_doi("https://doi.org/10.1038/ABC") == "10.1038/abc"
    assert normalize_doi("doi:10.1/x") == "10.1/x"
    assert normalize_title("Self-driving <i>Lab</i>: Ångström!") == "self driving lab angstrom"


def test_openalex_parse_skips_errata_and_untitled(monkeypatch):
    monkeypatch.setattr(http, "get_json", lambda url, params=None: OA)
    papers = list(openalex.recent_works(ID2NAME, "2026-07-01"))
    assert [p.title[:20] for p in papers] == ["Self-driving laborat", "Bayesian optimizatio"]
    p = papers[0]
    assert p.doi == "10.1038/s41586-026-00001-1"
    assert p.tracked_authors == ["Alán Aspuru-Guzik", "Anatole von Lilienfeld"]
    assert p.abstract == "We built a lab."
    assert p.venue == "Nature"
    assert papers[1].arxiv_id == "2609.01234"  # derived from the arXiv DOI


def test_openalex_query_uses_date_filter_cursor_and_no_truncation(monkeypatch):
    calls = []
    pages = [dict(OA, meta={"next_cursor": "c2"}), dict(OA, meta={"next_cursor": None})]
    monkeypatch.setattr(http, "get_json", lambda url, params=None: calls.append(params) or pages[len(calls) - 1])
    assert len(list(openalex.recent_works(ID2NAME, "2026-07-01"))) == 4
    f = calls[0]["filter"]
    assert "author.id:A5000000001|A5000000002" in f and "from_publication_date:2026-07-01" in f
    assert calls[0]["cursor"] == "*" and calls[1]["cursor"] == "c2"
    assert calls[0]["sort"] == "publication_date:desc"


def test_arxiv_parse():
    ps = arxiv.parse_feed((FX / "arxiv_feed.xml").read_bytes(), "Anatole von Lilienfeld", "2026-07-01")
    assert [p.arxiv_id for p in ps] == ["2609.01234", "2610.00007"]  # version stripped, old one dropped
    assert ps[0].title == "Bayesian Optimization Under Budget Constraints"
    assert ps[0].date == "2026-09-14"


def test_scholar_alert_parse():
    ps = scholar_email.parse_alert((FX / "scholar_alert.html").read_text(),
                                   "Anatole von Lilienfeld - new articles")
    assert len(ps) == 2
    assert ps[0].title == "Brand new preprint on molecular graphs"
    assert ps[0].url == "https://arxiv.org/pdf/2610.00007"
    assert ps[0].arxiv_id == "2610.00007"
    assert ps[0].tracked_authors == ["Anatole von Lilienfeld"]
    assert ps[1].doi == "10.1021/jacs.6b00042"
    assert ps[1].title == "Electrocatalysts & robots: a review"
    assert ps[1].venue == "Journal of the American Chemical Society"


def test_slack_message_escapes():
    m = slack.format_message(Paper(title="A & B <c> | d", url="https://x", tracked_authors=["X"],
                                   authors=["X"], sources=["openalex"], summary="s"))
    text = m["blocks"][0]["text"]["text"]
    assert "A &amp; B &lt;c&gt; ¦ d" in text and "<https://x|" in text and "> s" in text


def test_batch_dedup_merges_across_sources():
    a = Paper(title="Same Title!", doi="10.48550/arxiv.2609.01234", sources=["openalex"], tracked_authors=["A"])
    b = Paper(title="same title", arxiv_id="2609.01234v3", sources=["arxiv"], tracked_authors=["B"])
    out = dedup_batch([a, b])
    assert len(out) == 1 and out[0].sources == ["openalex", "arxiv"] and out[0].tracked_authors == ["A", "B"]


# ---------------------------------------------------------------- end to end

class FakeWeb:
    """Routes the single http.request choke point; records Slack posts."""

    def __init__(self):
        self.works = copy.deepcopy(OA)
        self.arxiv = (FX / "arxiv_feed.xml").read_bytes()
        self.slack_posts, self.fail = [], set()
        self.slack_status = 200
        self.llm = None

    def __call__(self, url, params=None, *, data=None, headers=None, retries=4):
        for key in self.fail:
            if key in url:
                raise urllib.error.URLError(f"{key} down")
        if "api.openalex.org/works" in url:
            return json.dumps(self.works).encode()
        if "api.openalex.org/authors/orcid:" in url:
            if "0000-0000-0000-0000" in url:
                raise urllib.error.HTTPError(url, 404, "nf", {}, None)
            return json.dumps({"id": "https://openalex.org/A5000000001", "display_name": "Alán Aspuru-Guzik"}).encode()
        if "api.openalex.org/authors" in url:
            return json.dumps({"results": [{"id": "https://openalex.org/A9", "display_name": "J Smith",
                                            "works_count": 3, "last_known_institutions": []}]}).encode()
        if "export.arxiv.org" in url:
            return self.arxiv
        if "api.crossref.org" in url:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        if "hooks.slack.com" in url:
            if self.slack_status != 200:
                raise urllib.error.HTTPError(url, self.slack_status, "bad", {}, None)
            self.slack_posts.append(json.loads(data))
            return b"ok"
        if "api.anthropic.com" in url:
            if self.llm is None:
                raise urllib.error.URLError("llm down")
            return json.dumps({"content": [{"type": "text", "text": json.dumps(self.llm)}]}).encode()
        raise AssertionError(f"unexpected url {url}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    web = FakeWeb()
    monkeypatch.setattr(http, "request", web)
    monkeypatch.setattr("paper_monitor.cli.time.sleep", lambda s: None)
    for k in ("SLACK_WEBHOOK_URL", "ANTHROPIC_API_KEY", "IMAP_HOST", "PAS_MONITOR_INGEST"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / "authors.csv").write_text(
        "name,orcid,openalex_ids,arxiv_query\n"
        "Alán Aspuru-Guzik,0000-0003-1024-3325,A5000000001,\n"
        "Anatole von Lilienfeld,,A5000000002,au:von_Lilienfeld_A\n")
    db = tmp_path / "state.db"

    def run(*extra):
        return main(["run", "--authors", str(tmp_path / "authors.csv"), "--db", str(db),
                     "--brief", str(tmp_path / "brief.txt"), *extra])

    def statuses():
        return dict(sqlite3.connect(db).execute("SELECT title_key, status FROM papers"))

    def outbox():
        return json.loads((tmp_path / "outbox" / "pending.json").read_text())

    return web, run, statuses, outbox, monkeypatch, tmp_path


def new_work(title, doi, date="2026-10-03"):
    return {"id": f"https://openalex.org/W{abs(hash(title))}", "doi": f"https://doi.org/{doi}",
            "title": title, "publication_date": date, "type": "article",
            "primary_location": {"source": {"display_name": "JACS"}},
            "authorships": [{"author": {"id": "https://openalex.org/A5000000001", "display_name": "A A-G"}}]}


def test_first_run_seeds_silently_then_only_new_papers_are_posted(env):
    web, run, statuses, outbox, mp, _ = env
    # Day 1: baseline. Nothing posted, no Slack needed.
    assert run() == 0
    assert set(statuses().values()) == {"seeded"} and len(statuses()) == 3
    assert outbox() == []

    # Day 2: one genuinely new journal paper appears. Slack not connected yet.
    web.works["results"].append(new_work("Robotic electrolyte screening", "10.1021/jacs.6c01"))
    assert run() == 0
    assert statuses()["robotic electrolyte screening"] == "pending"
    assert len(outbox()) == 1 and web.slack_posts == []

    # Day 3: webhook added -> the queued paper goes out exactly once.
    mp.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    assert run() == 0
    assert len(web.slack_posts) == 1
    assert "Robotic electrolyte screening" in web.slack_posts[0]["blocks"][0]["text"]["text"]
    assert statuses()["robotic electrolyte screening"] == "posted"

    # Day 4: same data again -> no reposts.
    assert run() == 0
    assert len(web.slack_posts) == 1


def test_preprint_then_journal_version_is_not_reposted(env):
    web, run, statuses, _, mp, tmp = env
    mp.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    assert run() == 0  # seed
    web.works["results"].append(new_work("Graph networks for MOFs", "10.48550/arxiv.2610.11111"))
    assert run() == 0
    assert len(web.slack_posts) == 1
    # Journal version: new DOI, same title (different case/punctuation).
    web.works["results"].append(new_work("Graph Networks for MOFs.", "10.1039/d6sc00001"))
    assert run() == 0
    assert len(web.slack_posts) == 1
    row = sqlite3.connect(tmp / "state.db").execute(
        "SELECT doi, arxiv_id FROM papers WHERE title_key='graph networks for mofs'").fetchone()
    assert row == ("10.48550/arxiv.2610.11111", "2610.11111")


def test_slack_failure_keeps_items_pending_and_fails_run(env):
    web, run, statuses, _, mp, _ = env
    assert run() == 0
    web.works["results"].append(new_work("Paper X", "10.1/x"))
    mp.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    web.slack_status = 404
    assert run() == 1
    assert statuses()["paper x"] == "pending"
    web.slack_status = 200
    assert run() == 0
    assert statuses()["paper x"] == "posted"


def test_one_source_down_others_still_work_and_run_reports_error(env):
    web, run, statuses, _, _, _ = env
    assert run() == 0
    web.works["results"].append(new_work("Paper Y", "10.1/y"))
    web.fail.add("export.arxiv.org")
    assert run() == 1
    assert statuses()["paper y"] == "pending"


def test_first_run_with_failing_source_does_not_seed(env):
    web, run, statuses, _, _, tmp = env
    web.fail.add("api.openalex.org")
    assert run() == 1
    assert statuses() == {}


def test_post_backlog_posts_window_on_first_run(env):
    web, run, statuses, _, mp, _ = env
    mp.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    assert run("--post-backlog") == 0
    assert len(web.slack_posts) == 3


def test_llm_relevance_filter_and_fail_open(env):
    web, run, statuses, _, mp, tmp = env
    assert run() == 0
    mp.setenv("ANTHROPIC_API_KEY", "k")
    (tmp / "brief.txt").write_text("Self-driving labs and catalysis.")
    web.llm = {"relevant": False, "summary": "Off topic."}
    web.works["results"].append(new_work("Medieval poetry corpus", "10.1/poem"))
    assert run() == 0
    assert statuses()["medieval poetry corpus"] == "irrelevant"

    web.llm = {"relevant": True, "summary": "Robots find catalysts fast."}
    web.works["results"].append(new_work("Robot catalysts", "10.1/rc"))
    assert run() == 0
    mp.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    assert run() == 0
    assert "Robots find catalysts fast." in web.slack_posts[0]["blocks"][0]["text"]["text"]

    web.llm = None  # LLM outage -> paper still queued
    web.works["results"].append(new_work("Another paper", "10.1/ap"))
    assert run() == 0
    assert statuses()["another paper"] == "posted"


def test_resolve_fills_orcid_rows_and_lists_candidates_for_names(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(http, "request", FakeWeb())
    p = tmp_path / "authors.csv"
    p.write_text("name,orcid,openalex_ids,arxiv_query\n"
                 "Alán Aspuru-Guzik,0000-0003-1024-3325,,\n"
                 "John Smith,,,\n")
    assert main(["resolve", str(p)]) == 1  # one still unresolved
    out = capsys.readouterr().out
    assert "OK    Alán Aspuru-Guzik: A5000000001" in out
    assert "PICK  John Smith" in out and "A9  J Smith" in out
    rows = p.read_text().splitlines()
    assert rows[1].startswith("Alán Aspuru-Guzik,0000-0003-1024-3325,A5000000001")
    assert rows[2] == "John Smith,,,"


def test_crossref_overrides_title_and_venue(monkeypatch):
    from paper_monitor import crossref
    monkeypatch.setattr(http, "get_json", lambda url, params=None: {
        "message": {"title": ["Canonical  Title"], "container-title": ["Nature Chemistry"]}})
    p = Paper(title="canonical title", doi="10.1/abc", sources=["openalex"])
    crossref.enrich(p)
    assert (p.title, p.venue, p.sources) == ("Canonical Title", "Nature Chemistry", ["openalex", "crossref"])
    arx = Paper(title="t", doi="10.48550/arxiv.1", sources=[])
    crossref.enrich(arx)  # arXiv DOIs skipped (not Crossref)
    assert arx.sources == []
