"""P0 cloud canary: transaction-rolled-back identities against real PostgreSQL."""
import json
import os
import secrets
import time
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.db import engine, get_session
from app.main import app
from app.models.access import AdminGrant
from app.models.reading import Reader, ReaderSession
from app.services.reader_auth import COOKIE, digest
from paper_monitor.reading_smoke import main as reading_checks


def main():
    reading_checks()
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection, join_transaction_mode='create_savepoint')
        app.dependency_overrides[get_session] = lambda: db
        try:
            clients=[]; ids=[]; origin=os.environ['PAS_PUBLIC_URL'];team=os.environ['PAS_SLACK_TEAM_ID']
            for n in range(3):
                rid='p0_canary_'+secrets.token_hex(12);token=secrets.token_urlsafe(32);ids.append(rid)
                db.add(Reader(id=rid,workspace_id=team,slack_user_id=rid,name='P0 canary '+str(n),active=True));db.flush()
                db.add(ReaderSession(token_hash=digest(token),reader_id=rid,expires=int(time.time())+300))
                client=TestClient(app,base_url=origin,headers={'Origin':origin,'X-PAS-Request':'1'});client.cookies.set(COOKIE,token);clients.append(client)
            db.add(AdminGrant(reader_id=ids[0]));db.commit();a,b,c=clients
            anon=TestClient(app)
            for path in ['/access/check-admin','/access/members','/access/audit','/papers','/access/files/index.html']:
                assert anon.get(path).status_code==401,path
                assert b.get(path).status_code==403,path
            assert a.get('/access/check-admin').status_code==200
            assert a.get('/access/files/index.html').status_code==200
            assert b.get('/reading/papers').status_code==200
            assert a.put('/access/members/'+ids[1],json={'admin':True,'active':True}).status_code==200
            assert b.get('/access/check-admin').status_code==200
            assert a.put('/access/members/'+ids[1],json={'admin':False,'active':True}).status_code==200
            assert b.get('/access/check-admin').status_code==403
            private=b.post('/chat/sessions',json={'title':'Canary private'}).json()['id']
            assert a.get('/chat/sessions/'+private).status_code==404
            assert a.put('/access/members/'+ids[1],json={'admin':False,'active':False}).status_code==200
            assert b.get('/reading/papers').status_code==401
            print(json.dumps({'access_canary':'passed','principals':3,'synthetic_data':'rolled_back','default_deny':True,'admin_private_bypass':False,'revoke_immediate':True}))
        finally:
            app.dependency_overrides.clear();db.close();transaction.rollback()


if __name__=='__main__':main()
