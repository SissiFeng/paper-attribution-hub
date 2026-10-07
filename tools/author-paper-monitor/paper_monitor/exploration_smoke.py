"""P2 real-paper canary; synthetic identities and research records roll back."""
import json
import os
import secrets
import time
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.db import engine, get_session
from app.main import app
from app.models import Paper
from app.models.access import AdminGrant
from app.models.reading import Reader, ReaderSession
from app.services.reader_auth import COOKIE, digest


def exercise(clients, identities, papers, prefix='', add_arrival=None):
    a,b,admin=clients;checks=[]
    def call(client,method,path,status=200,payload=None):
        r=client.request(method,prefix+path,**({'json':payload} if payload is not None else {}))
        assert r.status_code==status,(method,path,r.status_code,r.text[:200])
        assert 'no-store' in r.headers.get('cache-control','')
        checks.append((method,path,status));return r.json()
    project=call(a,'POST','/research/projects',201,{'title':'Temporary P2 verification','member_ids':[identities[1]]})
    pid=project['id'];base='/research/projects/'+pid;url=base+'/exploration'
    for p in papers:call(a,'PUT',base+'/papers/'+p['id'])
    found=call(a,'GET',url);exact=0
    assert {n['id'] for n in found['map']['nodes'] if n['kind']=='paper'}=={p['id'] for p in papers}
    for edge in found['map']['edges']:
        for anchor in edge['evidence']:
            source=call(a,'GET','/reading/papers/'+anchor['paper_id']+'/sources/'+anchor['kind']+'/'+anchor['source_id'])
            assert source['text'][anchor['start']:anchor['end']]==anchor['quote']
            exact+=1
    hypothesis=call(a,'POST',url+'/connections',201,{'source_id':papers[0]['id'],'target_id':papers[1]['id'],
        'relation':'method_transfer','rationale':'Temporary proposed connection, not a scientific finding.'})
    assert any(e.get('id')==hypothesis['id'] and e['kind']=='hypothesis' for e in call(b,'GET',url)['map']['edges'])
    call(b,'DELETE',url+'/connections/'+hypothesis['id'],403)
    related=call(a,'GET',url+'/related?q=catalyst,optimization')
    assert 'not semantic relevance' in related['basis']
    paper_id=papers[0]['id']
    for client,decision in [(a,'include'),(b,'exclude')]:
        call(client,'PUT',url+'/screening/'+paper_id,payload={'decision':decision,'reason':'Temporary independent judgement','version':0})
    call(a,'PUT',url+'/screening/'+paper_id,409,{'decision':'exclude','reason':'stale write','version':0})
    assert len(call(a,'GET',url)['screenings'])==2
    phrase='p2-verification-'+secrets.token_hex(8)
    watch={'terms':[phrase],'criteria':'Temporary test criteria','enabled':True,'version':0}
    call(b,'PUT',url+'/watch',403,watch);call(a,'PUT',url+'/watch',payload=watch)
    assert call(a,'POST',url+'/check')['new_alerts']==0
    if add_arrival:
        arrival=add_arrival(phrase)
        assert call(a,'POST',url+'/check')['new_alerts']==1
        assert call(b,'POST',url+'/check')['new_alerts']==0
        call(a,'POST',url+'/alerts/'+arrival+'/seen')
        assert call(a,'GET',url)['alerts'][0]['seen'] is True
        assert call(b,'GET',url)['alerts'][0]['seen'] is False
    call(admin,'GET',url,404);call(admin,'GET',url+'/related?q=catalyst',404)
    call(a,'PUT',base+'/members',payload={'member_ids':[]})
    for path in [url,url+'/related?q=catalyst']:
        call(b,'GET',path,404)
    call(b,'POST',url+'/check',404)
    call(b,'PUT',url+'/screening/'+paper_id,404,{'decision':'include','reason':'revoked','version':1})
    call(b,'DELETE',url+'/connections/'+hypothesis['id'],404)
    return {'checks':len(checks),'real_papers':len(papers),'exact_method_quotes':exact,
        'related_candidates':len(related['items']),'boundary':'Literal source matches and access verified; no claim of semantic retrieval, method adoption or scientific validation.'}


def main():
    from fastapi.testclient import TestClient
    from paper_monitor.research_smoke import main as previous, real_papers
    previous()
    with engine.connect() as connection:
        transaction=connection.begin();db=Session(bind=connection,join_transaction_mode='create_savepoint')
        app.dependency_overrides[get_session]=lambda:db
        clients=[]
        try:
            ids=[];origin=os.environ['PAS_PUBLIC_URL'];team=os.environ['PAS_SLACK_TEAM_ID']
            for n in range(3):
                rid='p2_canary_'+secrets.token_hex(12);token=secrets.token_urlsafe(32);ids.append(rid)
                db.add(Reader(id=rid,workspace_id=team,slack_user_id=rid,name='Temporary P2 canary '+str(n),active=True));db.flush()
                db.add(ReaderSession(token_hash=digest(token),reader_id=rid,expires=int(time.time())+900))
                client=TestClient(app,base_url=origin,headers={'Origin':origin,'X-PAS-Request':'1'});client.cookies.set(COOKIE,token);clients.append(client)
            db.add(AdminGrant(reader_id=ids[2]));db.commit()
            def arrival(phrase):
                pid='p2_canary_paper_'+secrets.token_hex(12)
                db.add(Paper(id=pid,title=phrase,source='openalex',created_at=datetime.now(UTC)));db.commit();return pid
            result=exercise(clients,ids,real_papers(db),add_arrival=arrival)
        finally:
            for client in clients:client.close()
            app.dependency_overrides.clear();db.close();transaction.rollback()
        print(json.dumps({'exploration_canary':'passed',**result,'synthetic_data':'rolled_back'}))


if __name__=='__main__':main()
