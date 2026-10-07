"""P1 acceptance against real papers and PostgreSQL; canary rows roll back."""
import json
import os
import secrets
import time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import engine, get_session
from app.main import app
from app.models import Paper, PaperSection
from app.models.access import AdminGrant
from app.models.reading import Reader, ReaderSession
from app.services.reader_auth import COOKIE, digest


def exercise(clients, identities, papers, prefix=''):
    a,b,admin=clients
    checked=[]
    def request(client, method, path, status=200, payload=None):
        response=client.request(method,prefix+path,**({'json':payload} if payload is not None else {}))
        assert response.status_code==status,(method,path,response.status_code,response.text[:200])
        assert 'no-store' in response.headers.get('cache-control',''),path
        checked.append({'method':method,'path':path,'status':status})
        return response.json()
    project=request(a,'POST','/research/projects',201,{'title':'Temporary P1 acceptance','member_ids':[identities[1]]})
    pid=project['id']
    for paper in papers[:2]:request(a,'PUT',f'/research/projects/{pid}/papers/{paper["id"]}')
    source=request(a,'GET',f'/reading/papers/{papers[0]["id"]}/sources/section/{papers[0]["section_id"]}')
    start=next((i for i,c in enumerate(source['text']) if not c.isspace()),0)
    quote=source['text'][start:start+120]
    anchor={k:source[k] for k in ('kind','source_id','version')} | {'start':start,'end':start+len(quote),'quote':quote}
    n=request(a,'POST','/research/annotations',201,{'paper_id':papers[0]['id'],'anchor':anchor,'body':'Private acceptance note'})
    assert request(b,'GET','/research/annotations')==[]
    request(admin,'PUT','/research/annotations/'+n['id'],404,{'body':'denied'})
    copied=request(a,'POST','/research/annotations/'+n['id']+'/copy',201,{'project_id':pid})
    assert request(b,'GET','/research/annotations?project_id='+pid)[0]['body']=='Private acceptance note'
    request(b,'GET','/research/annotations')==[]
    ids=[p['id'] for p in papers[:2]]
    comparison=request(a,'POST','/research/comparisons',201,{'paper_ids':ids})
    request(admin,'GET','/research/comparisons/'+comparison['id'],404)
    shared=request(a,'POST','/research/comparisons/'+comparison['id']+'/copy',201,{'project_id':pid})
    request(b,'GET','/research/comparisons/'+shared['id'])
    private=request(a,'POST','/chat/sessions',201,{'title':'Private P1 acceptance','scope':{'paper_ids':ids,'page_context':'DO NOT COPY'}})
    request(a,'POST','/chat/sessions/'+private['id']+'/comments',201,{'query':'DO NOT SHARE'})
    msg=request(a,'POST','/chat/sessions/'+private['id']+'/comments',201,{'query':'Selected evidence only'})
    discussion=request(a,'POST',f'/research/projects/{pid}/discussions',201,{'paper_ids':ids,'source_session_id':private['id'],'message_ids':[msg['id']]})
    cid=discussion['id']
    chat=request(b,'GET','/chat/sessions/'+cid)
    assert [m['content'] for m in chat['messages']]==['Selected evidence only']
    assert chat['scope']['page_context'] is None
    request(b,'GET','/chat/sessions/'+private['id'],404)
    request(b,'POST','/chat/sessions/'+cid+'/comments',201,{'query':'Colleague reply'})
    request(b,'PUT',f'/research/projects/{pid}/members',403,{'member_ids':[identities[2]]})
    request(admin,'GET','/research/projects/'+pid,404)
    model=request(a,'GET','/reading/model')
    reply=request(b,'POST','/chat/sessions/'+cid+'/messages',200,{'query':'Which published passages describe the methods and results?'})
    for item in reply['assistant_message']['sources']:
        assert 'anchor' in item
    request(a,'PUT',f'/research/projects/{pid}/members',200,{'member_ids':[]})
    for path in [f'/research/projects/{pid}',f'/research/comparisons/{shared["id"]}',f'/research/annotations?project_id={pid}',f'/chat/sessions/{cid}',f'/chat/sessions/{cid}/members']:
        request(b,'GET',path,404)
    request(b,'POST','/chat/sessions/'+cid+'/messages',404,{'query':'methods'})
    request(b,'DELETE','/research/annotations/'+copied['id'],404)
    assert request(b,'GET','/research/projects')==[]
    assert request(b,'GET','/chat/sessions')==[]
    # A bounded real-corpus pilot checks exact quotations and scope, not scientific entailment.
    quote_count=0;matrix_count=0
    for i in range(0,len(papers)-1,2):
        pair=papers[i:i+2]
        result=request(a,'POST','/research/comparisons',201,{'paper_ids':[p['id'] for p in pair],'dimensions':['Methods','Conditions','Results','Limitations']})
        matrix_count+=1
        docs={}
        for cell in result['cells']:
            for anchor in cell['evidence']:
                key=(cell['paper_id'],anchor['kind'],anchor['source_id'])
                if key not in docs:docs[key]=request(a,'GET',f'/reading/papers/{key[0]}/sources/{key[1]}/{key[2]}')
                doc=docs[key]
                assert anchor['quote']==doc['text'][anchor['start']:anchor['end']]
                assert anchor['version']==doc['version']
                quote_count+=1
    return {'checks':len(checked),'real_papers':len(papers),'matrices':matrix_count,'exact_quotes':quote_count,
            'model':model,'answer_model':reply['assistant_message']['model'],
            'answer_sources':len(reply['assistant_message']['sources']),
            'boundary':'Exact source offsets and access were tested; scientific entailment and fair ranking are not automatically certified.'}


def real_papers(db):
    # One sufficiently long section per unique real paper, ordered reproducibly.
    found={}
    for pid,sid,title,content in db.execute(select(Paper.id,PaperSection.id,Paper.title,PaperSection.content).join(PaperSection).order_by(Paper.id,PaperSection.order_index)):
        if pid not in found and content and len(content)>150:
            found[pid]={'id':pid,'section_id':sid,'title':title}
        if len(found)==20:break
    assert len(found)>=2,'Need two real papers with indexed sources.'
    return list(found.values())


def main():
    from fastapi.testclient import TestClient
    from paper_monitor.access_smoke import main as previous_checks
    previous_checks()
    with TestClient(app) as anonymous:
        public=anonymous.get('/catalog/papers').json()['items']
        assert public, 'Expected real published records in the catalogue.'
        expected={'id','title','abstract','doi','year','venue','authors','keywords','full_text_available'}
        assert all(set(p)==expected for p in public)
        sample=public[0]
        assert anonymous.get('/catalog/papers/'+sample['id']).json()['id']==sample['id']
        assert anonymous.get('/reading/papers/'+sample['id']+'/markdown').status_code==401
        assert anonymous.get('/research/projects').status_code==401
        shared=anonymous.get('/catalog/paper-view?limit=5')
        assert shared.status_code==200,shared.text[:200]
        assert shared.json()
        for record in shared.json():
            assert record['review'] is None
            detail=anonymous.get('/catalog/papers/'+record['id']+'/view')
            assert detail.status_code==200 and detail.json()['id']==record['id']
            wiki=anonymous.get('/catalog/papers/'+record['id']+'/wiki')
            assert wiki.status_code==200,wiki.text[:200]
            assert wiki.json()['sections']
            assert not {'review_notes','retrieval_provenance','attribution_review'} & {part['key'] for part in wiki.json()['sections']}
        print(json.dumps({'shared_original_paper_view':'passed','real_wikis':len(shared.json())}))
        print(json.dumps({'public_catalogue':'passed','sample_id':sample['id'],'private_routes_protected':True}))
    with engine.connect() as connection:
        transaction=connection.begin();db=Session(bind=connection,join_transaction_mode='create_savepoint')
        app.dependency_overrides[get_session]=lambda:db
        clients=[]
        try:
            ids=[];origin=os.environ['PAS_PUBLIC_URL'];team=os.environ['PAS_SLACK_TEAM_ID']
            for n in range(3):
                rid='p1_canary_'+secrets.token_hex(12);token=secrets.token_urlsafe(32);ids.append(rid)
                db.add(Reader(id=rid,workspace_id=team,slack_user_id=rid,name='Temporary P1 canary '+str(n),active=True));db.flush()
                db.add(ReaderSession(token_hash=digest(token),reader_id=rid,expires=int(time.time())+600))
                client=TestClient(app,base_url=origin,headers={'Origin':origin,'X-PAS-Request':'1'});client.cookies.set(COOKIE,token);clients.append(client)
            db.add(AdminGrant(reader_id=ids[2]));db.commit()
            result=exercise(clients,ids,real_papers(db))
            print(json.dumps({'research_canary':'passed',**result,'synthetic_data':'rolled_back'}))
        finally:
            for client in clients:client.close()
            app.dependency_overrides.clear();db.close();transaction.rollback()


if __name__=='__main__':main()
