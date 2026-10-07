"""Cloud acceptance check against the live PAS schema, always rolled back."""
import contextlib
import json

from .pas import ingest_session
from .store import Store


def verify(path):
    from sqlalchemy import func, select
    from app.db import SessionLocal
    from app.models import Paper

    with contextlib.closing(Store(path)) as store, SessionLocal() as session:
        before = session.scalar(select(func.count(Paper.id)))
        try:
            for _, p in store.rows("SELECT id,data FROM papers ORDER BY id"):
                if p.doi and session.scalar(select(Paper.id).where(Paper.doi == p.doi)):
                    continue
                receipt = ingest_session(session, p, "main")
                assert session.get(Paper, receipt).title == p.title
                assert ingest_session(session, p, "main") == receipt
                assert session.scalar(select(func.count(Paper.id))) == before + 1
                session.rollback()
                after = session.scalar(select(func.count(Paper.id)))
                assert before == after
                print(json.dumps({"pas_transaction_test": "passed", "paper_id": receipt,
                                  "title": p.title, "count_before": before,
                                  "count_after_rollback": after, "durable_insert": False}))
                return
            raise ValueError("No new live paper available for ingestion verification")
        finally:
            session.rollback()
