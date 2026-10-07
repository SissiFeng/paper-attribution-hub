"""Explicitly authenticated client for legacy administrative API contract tests.

Authorization tests deliberately use the ordinary TestClient instead. This
helper uses real reader sessions/grants; it does not disable the API gate.
"""
import os
import secrets
import time
from fastapi.testclient import TestClient


class AdminTestClient(TestClient):
    def __init__(self, app, **kwargs):
        from app.db import engine, init_database, SessionLocal
        from app.models.reading import Reader, ReaderSession
        from app.models.access import AdminGrant
        from app.services.reader_auth import COOKIE, digest
        if engine.dialect.name != 'sqlite':
            raise RuntimeError('Synthetic API test identities require the isolated SQLite test database.')
        init_database()
        origin = os.environ.setdefault('PAS_PUBLIC_URL', 'https://pas.test')
        team = os.environ.setdefault('PAS_SLACK_TEAM_ID', 'T1')
        token = secrets.token_urlsafe(32)
        rid = 'test_admin_' + secrets.token_hex(8)
        with SessionLocal() as db:
            db.add(Reader(id=rid, workspace_id=team, slack_user_id=rid, name='API test admin', active=True))
            db.flush()
            db.add(ReaderSession(token_hash=digest(token), reader_id=rid, expires=int(time.time()) + 3600))
            db.add(AdminGrant(reader_id=rid)); db.commit()
        headers = {'Origin': origin, 'X-PAS-Request': '1', **kwargs.pop('headers', {})}
        super().__init__(app, headers=headers, **kwargs)
        self.cookies.set(COOKIE, token)
