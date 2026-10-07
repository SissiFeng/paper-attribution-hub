"""Cloud isolation canary: real PostgreSQL and API, all synthetic data rolled back."""
import json
import os
import secrets
import time
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import engine, get_session
from app.main import app
from app.models import Paper
from app.models.reading import Reader, ReaderSession
from app.services.reader_auth import COOKIE, digest


def main():
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection, join_transaction_mode='create_savepoint')
        app.dependency_overrides[get_session] = lambda: db
        try:
            origin = os.environ['PAS_PUBLIC_URL'];team = os.environ['PAS_SLACK_TEAM_ID']
            clients=[];ids=[]
            for n in range(3):
                rid='canary_'+secrets.token_hex(12); token=secrets.token_urlsafe(32); ids.append(rid)
                db.add(Reader(id=rid,workspace_id=team,slack_user_id=rid,name='Canary '+str(n),active=True));db.flush()
                db.add(ReaderSession(token_hash=digest(token),reader_id=rid,expires=int(time.time())+300));db.commit()
                client=TestClient(app,base_url=origin,headers={'Origin':origin,'X-PAS-Request':'1'});client.cookies.set(COOKIE,token);clients.append(client)
            a,b,c=clients
            assert TestClient(app).get('/reading/papers').status_code==401
            papers=a.get('/reading/papers').json()['items'];assert papers
            pid=papers[0]['id']
            assert a.get('/reading/papers/'+pid).status_code==200
            assert a.put('/reading/saved/'+pid,json={'note':'PRIVATE CANARY'}).status_code==200
            assert b.get('/reading/papers/'+pid).json()['note']==''
            created=a.post('/chat/sessions',json={'title':'Canary private','scope':{'paper_ids':[pid]}});assert created.status_code==201,created.text
            chat=created.json()['id'];assert b.get('/chat/sessions/'+chat).status_code==404
            secret=a.post(f'/chat/sessions/{chat}/comments',json={'query':'PRIVATE CANARY SECRET'});assert secret.status_code==201
            count=a.post(f'/chat/sessions/{chat}/messages',json={'query':'How many papers are in the current scope?'});assert count.status_code==200,count.text
            group=a.post(f'/chat/sessions/{chat}/share',json={'title':'Canary shared','member_ids':[ids[1]],'message_ids':[]});assert group.status_code==201,group.text
            gid=group.json()['id'];assert b.get('/chat/sessions/'+gid).json()['messages']==[]
            assert c.get('/chat/sessions/'+gid).status_code==404
            assert b.post(f'/chat/sessions/{gid}/comments',json={'query':'Group comment'}).status_code==201
            assert a.put(f'/chat/sessions/{gid}/members',json={'member_ids':[]}).status_code==200
            assert b.get('/chat/sessions/'+gid).status_code==404
            second=next(p['id'] for p in papers if p['id']!=pid)
            assert a.post('/reading/compare',json={'paper_ids':[pid,second]}).status_code==200
            full=db.scalar(select(Paper).where(Paper.full_text_available.is_(True)).limit(1))
            md_source=None
            if full:
                md=a.get('/reading/papers/'+full.id+'/markdown');assert md.status_code==200,md.text[:500];md_source=md.json()['source']
                reader=a.post('/chat/sessions',json={'scope':{'paper_ids':[full.id]}}).json()['id']
                response=a.post(f'/chat/sessions/{reader}/messages',json={'query':'Explain the main scientific evidence and limitations in this paper.'})
                assert response.status_code==200,response.text[:500]
                result=response.json()['assistant_message']
                assert all(s['paper_id']==full.id for s in result['sources'])
            else: result={}
            print(json.dumps({'isolation_canary':'passed','principals':3,'synthetic_data':'rolled_back','sample_paper':pid,'markdown_source':md_source,'answer_kind':result.get('answer_kind'),'answer_model':result.get('model'),'sources':len(result.get('sources',[]))}))
        finally:
            app.dependency_overrides.clear();db.close();transaction.rollback()


if __name__=='__main__': main()
