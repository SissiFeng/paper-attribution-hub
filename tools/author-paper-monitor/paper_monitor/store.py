"""Durable discovery, identifier aliases and independent PAS/Slack delivery state."""
from __future__ import annotations

import dataclasses
import datetime
import json
import sqlite3
from pathlib import Path

from .models import Paper, title_matches

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
  id INTEGER PRIMARY KEY,
  doi TEXT, arxiv_id TEXT, title_key TEXT,
  data TEXT NOT NULL, status TEXT NOT NULL, first_seen TEXT NOT NULL,
  posted_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_title ON papers(title_key);
CREATE TABLE IF NOT EXISTS identifiers (
  kind TEXT NOT NULL, value TEXT NOT NULL, paper_id INTEGER NOT NULL,
  PRIMARY KEY(kind,value,paper_id)
);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ingestion (paper_id INTEGER PRIMARY KEY, pas_id TEXT);
CREATE TABLE IF NOT EXISTS notification_receipts (paper_id INTEGER PRIMARY KEY, channel TEXT NOT NULL, ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries (
  paper_id INTEGER NOT NULL, user_id TEXT NOT NULL, channel TEXT NOT NULL,
  status TEXT NOT NULL, first_seen TEXT NOT NULL, posted_at TEXT, ts TEXT,
  PRIMARY KEY(paper_id,user_id)
);
CREATE INDEX IF NOT EXISTS ix_deliveries_user_status ON deliveries(user_id,status);
"""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def keys(p: Paper):
    return [("doi", d) for d in p.doi_aliases] + [
        (k, v) for k, v in (("arxiv", p.arxiv_id), ("openalex", p.openalex_id)) if v]


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.db.execute(
            "INSERT OR IGNORE INTO ingestion(paper_id) "
            "SELECT id FROM papers WHERE status!='seeded'"
        )
        # Backfill old databases once; retain both their column and JSON identifiers.
        if self.meta("alias_schema") != "1":
            for i, doi, arxiv, data in self.db.execute("SELECT id,doi,arxiv_id,data FROM papers").fetchall():
                paper = Paper(**json.loads(data))
                paper.merge(Paper(title=paper.title, doi=doi, arxiv_id=arxiv))
                self.add_ids(i, paper)
            if not self.is_empty():
                self.set_meta("initialized", "1")
            self.set_meta("alias_schema", "1")
            self.commit()

    def close(self):
        self.db.close()

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str):
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, value))

    def is_empty(self) -> bool:
        return self.db.execute("SELECT 1 FROM papers LIMIT 1").fetchone() is None

    def find(self, p: Paper) -> int | None:
        for kind, value in keys(p):
            row = self.db.execute(
                "SELECT paper_id FROM identifiers WHERE kind=? AND value=? ORDER BY paper_id",
                (kind, value)).fetchone()
            if row:
                return row[0]
        for i, data in self.db.execute("SELECT id,data FROM papers WHERE title_key=?", (p.title_key,)):
            if title_matches(Paper(**json.loads(data)), p):
                return i
        return None

    def add_ids(self, row_id: int, p: Paper) -> None:
        old = self.db.execute("SELECT data FROM papers WHERE id=?", (row_id,)).fetchone()
        merged = Paper(**json.loads(old[0]))
        merged.merge(p)
        if p.summary:
            merged.summary = p.summary
        if dataclasses.asdict(merged) != json.loads(old[0]):
            self.db.execute("UPDATE ingestion SET pas_id=NULL WHERE paper_id=?", (row_id,))
        for kind, value in keys(merged) + keys(p):
            self.db.execute("INSERT OR IGNORE INTO identifiers VALUES (?,?,?)", (kind, value, row_id))
        self.db.execute("UPDATE papers SET doi=?,arxiv_id=?,data=? WHERE id=?",
                        (merged.doi, merged.arxiv_id, json.dumps(dataclasses.asdict(merged)), row_id))

    def insert(self, p: Paper, status: str) -> int:
        row = self.db.execute(
            "INSERT INTO papers(doi,arxiv_id,title_key,data,status,first_seen) VALUES(?,?,?,?,?,?)",
            (p.doi, p.arxiv_id, p.title_key, json.dumps(dataclasses.asdict(p)), status, _now()))
        row_id = row.lastrowid
        self.add_ids(row_id, p)
        self.db.execute("INSERT INTO ingestion(paper_id) VALUES (?)", (row_id,))
        return row_id

    def pending(self, limit: int) -> list[tuple[int, Paper]]:
        return self.rows("SELECT id,data FROM papers WHERE status='pending' ORDER BY id LIMIT ?", (limit,))

    def rows(self, sql: str, args=()) -> list[tuple[int, Paper]]:
        return [(i, Paper(**json.loads(d))) for i, d in self.db.execute(sql, args)]

    def posted_between(self, start, end):
        return self.rows("SELECT id,data FROM papers WHERE status='posted' AND posted_at>=? AND posted_at<? ORDER BY posted_at,id", (start, end))

    def unsynced(self):
        return self.rows("SELECT p.id,p.data FROM papers p JOIN ingestion i ON i.paper_id=p.id WHERE i.pas_id IS NULL ORDER BY p.id")

    def mark_synced(self, row_id: int, pas_id: str):
        self.db.execute("UPDATE ingestion SET pas_id=? WHERE paper_id=?", (pas_id, row_id))
        self.commit()

    def set_status(self, row_id: int, status: str):
        self.db.execute("UPDATE papers SET status=? WHERE id=?", (status, row_id))
        self.commit()

    def mark_posted(self, row_id: int) -> None:
        self.db.execute("UPDATE papers SET status='posted',posted_at=? WHERE id=?", (_now(), row_id))
        self.commit()

    def mark_notified(self, row_id: int, channel: str, ts: str) -> None:
        self.db.execute('INSERT OR REPLACE INTO notification_receipts VALUES (?,?,?)', (row_id, channel, ts))
        self.mark_posted(row_id)

    def counts(self) -> dict[str, int]:
        return dict(self.db.execute("SELECT status,COUNT(*) FROM papers GROUP BY status"))

    def commit(self) -> None:
        self.db.commit()
