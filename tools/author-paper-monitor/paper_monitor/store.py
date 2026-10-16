"""Durable discovery, identifier aliases and independent PAS/Slack delivery state."""
from __future__ import annotations

import dataclasses
import datetime
import json
import hashlib
import sqlite3
import tempfile
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
        self._archive_tmp = tempfile.TemporaryDirectory() if str(path) == ':memory:' else None
        self.archive = Path(self._archive_tmp.name) if self._archive_tmp else Path(path).parent / 'mail-raw'
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        from .mailbox_state import SCHEMA as MAIL_SCHEMA
        self.db.executescript(MAIL_SCHEMA)
        columns = {r[1] for r in self.db.execute('PRAGMA table_info(ingestion)')}
        for name, declaration in [('needs_sync', 'INTEGER NOT NULL DEFAULT 0'), ('canonical_id', 'TEXT')]:
            if name not in columns:
                self.db.execute(f'ALTER TABLE ingestion ADD COLUMN {name} {declaration}')
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
        from .pas import paper_id
        for row_id, data, pas_id in self.db.execute('SELECT p.id,p.data,i.pas_id FROM papers p JOIN ingestion i ON p.id=i.paper_id WHERE i.canonical_id IS NULL').fetchall():
            self.db.execute('UPDATE ingestion SET canonical_id=? WHERE paper_id=?', (pas_id or paper_id(Paper(**json.loads(data))), row_id))

    def archive_mail(self, raw: bytes) -> str:
        digest = hashlib.sha256(raw).hexdigest()
        self.archive.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.archive / (digest + '.eml')
        if not path.exists():
            with path.open('wb') as out:
                path.chmod(0o600)
                out.write(raw)
        return digest

    def read_mail(self, digest: str) -> bytes:
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid mail content hash')
        raw = (self.archive / (digest + '.eml')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Mail content checksum mismatch')
        return raw

    def delete_mail(self, digest: str):
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid mail content hash')
        (self.archive / (digest + '.eml')).unlink(missing_ok=True)

    def close(self):
        self.db.close()
        if self._archive_tmp:
            self._archive_tmp.cleanup()

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
            self.db.execute("UPDATE ingestion SET needs_sync=1 WHERE paper_id=?", (row_id,))
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
        from .pas import paper_id
        self.db.execute("INSERT INTO ingestion(paper_id,canonical_id) VALUES (?,?)", (row_id, paper_id(p)))
        return row_id

    def pending(self, limit: int) -> list[tuple[int, Paper]]:
        return self.rows("SELECT id,data FROM papers WHERE status='pending' ORDER BY id LIMIT ?", (limit,))

    def rows(self, sql: str, args=()) -> list[tuple[int, Paper]]:
        return [(i, Paper(**json.loads(d))) for i, d in self.db.execute(sql, args)]

    def posted_between(self, start, end):
        return self.rows("SELECT id,data FROM papers WHERE status='posted' AND posted_at>=? AND posted_at<? ORDER BY posted_at,id", (start, end))

    def unsynced(self):
        return self.rows("SELECT p.id,p.data FROM papers p JOIN ingestion i ON i.paper_id=p.id WHERE i.pas_id IS NULL OR i.needs_sync=1 ORDER BY p.id")

    def ingestion_id(self, row_id):
        row = self.db.execute('SELECT COALESCE(pas_id,canonical_id) FROM ingestion WHERE paper_id=?', (row_id,)).fetchone()
        return row[0] if row else None

    def mark_synced(self, row_id: int, pas_id: str):
        self.db.execute("UPDATE ingestion SET pas_id=?,canonical_id=?,needs_sync=0 WHERE paper_id=?", (pas_id, pas_id, row_id))
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
