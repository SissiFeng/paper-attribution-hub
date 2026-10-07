import json
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from app.models import ChatSession, Paper
from app.models.reading import Reader, ReaderSession
from app.services import reader_auth as auth

ORIGIN = 'https://pas.test'


def signed_client(db, identity, team='T1'):
    from app.main import app
    user = Reader(id=identity, workspace_id=team, slack_user_id='U'+identity, name=identity, active=True)
    db.add(user)
    token = secrets.token_urlsafe(32)
    db.add(ReaderSession(token_hash=auth.digest(token), reader_id=identity, expires=int(time.time())+1000))
    db.commit()
    client = TestClient(app, base_url=ORIGIN, headers={'Origin': ORIGIN, 'X-PAS-Request': '1'})
    client.cookies.set(auth.COOKIE, token)
    return client


@pytest.fixture
def clients(session, monkeypatch):
    monkeypatch.setenv('PAS_PUBLIC_URL', ORIGIN)
    monkeypatch.setenv('PAS_SLACK_TEAM_ID', 'T1')
    a, b, c = (signed_client(session, n) for n in ('Alice', 'Bob', 'Carol'))
    session.add_all([Paper(id='P1', title='One paper', doi='10.1/one'), Paper(id='P2', title='Another paper')])
    session.commit()
    return a, b, c


def new_chat(client):
    result = client.post('/chat/sessions', json={'title':'Private notes','scope':{'paper_ids':['P1'], 'page_context':'private context'}})
    assert result.status_code == 201, result.text
    return result.json()['id']


def test_private_chat_rejects_other_users_on_every_path(clients):
    a,b,c = clients
    cid = new_chat(a)
    for client in (b,c):
        assert client.get('/chat/sessions').json() == []
        for suffix, method, payload in [('', 'get', None),('/messages','post',{'query':'What is new?'}),
            ('/messages/stream','post',{'query':'What is new?'}),('/comments','post',{'query':'hello'}),
            ('/members','get',None),('/members','put',{'member_ids':[]}),
            ('/share','post',{'title':'steal','member_ids':['Carol']})]:
            response = getattr(client, method)('/chat/sessions/'+cid+suffix, **({'json':payload} if payload else {}))
            assert response.status_code == 404, (suffix,response.text)
    assert a.get('/chat/sessions/'+cid).status_code == 200


def test_shared_copy_contains_only_chosen_messages_and_members_can_be_revoked(clients):
    a,b,c = clients
    cid = new_chat(a)
    secret = a.post(f'/chat/sessions/{cid}/comments', json={'query':'Private experiment idea'}).json()
    public = a.post(f'/chat/sessions/{cid}/comments', json={'query':'Let us discuss the published method'}).json()
    response = a.post(f'/chat/sessions/{cid}/share', json={'title':'Lab reading group','member_ids':['Bob'],'message_ids':[public['id']]})
    assert response.status_code == 201,response.text
    group = response.json()['id']
    shared = b.get('/chat/sessions/'+group).json()
    assert shared['scope']['page_context'] is None
    assert [m['content'] for m in shared['messages']] == [public['content']]
    assert secret['content'] not in json.dumps(shared)
    assert b.get('/chat/sessions/'+cid).status_code == 404
    assert c.get('/chat/sessions/'+group).status_code == 404
    assert b.post(f'/chat/sessions/{group}/comments',json={'query':'My public reply'}).status_code == 201
    assert b.put(f'/chat/sessions/{group}/members',json={'member_ids':['Carol']}).status_code == 403
    assert a.put(f'/chat/sessions/{group}/members',json={'member_ids':[]}).status_code == 200
    assert b.get('/chat/sessions/'+group).status_code == 404
    assert b.post(f'/chat/sessions/{group}/comments',json={'query':'Late reply'}).status_code == 404
    assert b.get('/chat/sessions').json() == []


def test_private_session_cannot_be_made_public_in_place(clients):
    a,b,_ = clients
    cid = new_chat(a)
    assert a.put(f'/chat/sessions/{cid}/members',json={'member_ids':['Bob']}).status_code == 422
    assert b.get('/chat/sessions/'+cid).status_code == 404


def test_share_rejects_foreign_messages_and_cross_workspace_members(clients, session):
    a,b,_ = clients
    cid = new_chat(a); other = new_chat(b)
    msg=b.post(f'/chat/sessions/{other}/comments',json={'query':'secret'}).json()
    assert a.post(f'/chat/sessions/{cid}/share',json={'title':'bad','member_ids':['Bob'],'message_ids':[msg['id']]}).status_code == 422
    signed_client(session,'Foreign',team='T2')
    assert a.post('/chat/sessions',json={'member_ids':['Foreign']}).status_code == 422
    assert a.post('/chat/sessions',json={'member_ids':['Unknown']}).status_code == 422


def test_unowned_legacy_chats_remain_inaccessible(clients, session):
    session.add(ChatSession(id='legacy',title='Old confidential chat',scope={}))
    session.commit()
    for client in clients:
        assert client.get('/chat/sessions/legacy').status_code == 404
        assert client.post('/chat/sessions/legacy/share',json={'title':'claim','member_ids':['Bob']}).status_code == 404


def test_bookmarks_notes_and_comparison_are_personal(clients):
    a,b,_ = clients
    assert a.put('/reading/saved/P1',json={'note':'Unpublished private plan'}).status_code == 200
    assert b.get('/reading/papers?saved=true').json()['items'] == []
    b.put('/reading/saved/P1',json={'note':'Bob private plan'})
    for client,note in ((a,'Unpublished private plan'),(b,'Bob private plan')):
        paper=client.get('/reading/papers/P1').json()
        assert paper['note']==note
        compared=client.post('/reading/compare',json={'paper_ids':['P1','P2']}).json()
        assert compared['papers'][0]['note']==note
    b.delete('/reading/saved/P1')
    assert a.get('/reading/papers/P1').json()['saved'] is True
    assert b.get('/reading/papers/P1').json()['saved'] is False
    assert a.post('/reading/compare',json={'paper_ids':['P1','P1']}).status_code==422
    assert a.get('/reading/papers/P1/markdown').status_code==404


def test_authentication_csrf_logout_and_workspace_boundary(clients, session):
    from app.main import app
    a,_,_=clients
    anonymous=TestClient(app,base_url=ORIGIN)
    for path in ('/auth/me','/chat/sessions','/reading/papers','/chat/members'):
        assert anonymous.get(path,headers={'X-User-ID':'Alice','X-API-Key':'anything'}).status_code==401
    assert a.post('/chat/sessions',json={},headers={'Origin':'https://evil.test'}).status_code==403
    assert a.post('/chat/sessions',json={},headers={'X-PAS-Request':''}).status_code==403
    foreign=signed_client(session,'Outsider','T2')
    assert foreign.get('/auth/me').status_code==401
    cookie=a.cookies.get(auth.COOKIE)
    assert a.post('/auth/logout').status_code==200
    anonymous.cookies.set(auth.COOKIE,cookie)
    assert anonymous.get('/auth/me').status_code==401


def test_expired_session_and_no_cache(clients, session):
    a,_,_=clients
    response=a.get('/reading/papers')
    assert response.headers['cache-control']=='no-store'
    login=session.get(ReaderSession,auth.digest(a.cookies.get(auth.COOKIE)))
    login.expires=0;session.commit()
    assert a.get('/reading/papers').status_code==401


class PairingTable:
    def __init__(self): self.rows={}
    def put_item(self,Item,**kw): self.rows[Item['pk']]=Item
    def get_item(self,Key,**kw): return {'Item':self.rows.get(Key['pk'],{})}
    def update_item(self,Key,ExpressionAttributeValues,**kw):
        from botocore.exceptions import ClientError
        row=self.rows[Key['pk']];values=ExpressionAttributeValues
        if row['version']!=values[':old']:
            raise ClientError({'Error':{'Code':'ConditionalCheckFailedException'}},'UpdateItem')
        row.update(payload=values[':p'],version=values[':new'])


def test_pairing_is_bound_to_browser_expires_and_can_only_be_consumed_once(clients, monkeypatch):
    from app.main import app
    table=PairingTable();monkeypatch.setattr(auth,'pairing_table',lambda:table)
    client=TestClient(app,base_url=ORIGIN,headers={'Origin':ORIGIN,'X-PAS-Request':'1'})
    response=client.post('/auth/connect')
    assert response.status_code==200
    assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
    code=response.json()['code'];cookie=client.cookies.get(auth.PAIR_COOKIE)
    assert client.post('/auth/connect/complete').json()=={'status':'pending'}
    item=next(iter(table.rows.values()));claim=json.loads(item['payload'])
    claim.update(status='verified',team_id='T1',user_id='UVERIFIED',name='Verified person')
    item['payload']=json.dumps(claim)
    with pytest.raises(Exception) as exc: auth.finish_pairing(code+'.attacker-verifier')
    assert exc.value.status_code==401
    assert client.post('/auth/connect/complete').json()['status']=='signed_in'
    assert client.get('/auth/me').json()['name']=='Verified person'
    with pytest.raises(Exception) as exc: auth.finish_pairing(cookie)
    assert exc.value.status_code==401
    claim.update(status='verified',expires=0);item['payload']=json.dumps(claim)
    with pytest.raises(Exception) as exc: auth.finish_pairing(cookie)
    assert exc.value.status_code==401


def test_markdown_provenance_integrity_and_indexed_fallback(clients, session, monkeypatch):
    import hashlib
    from app.models import PaperSection
    from app.services import s3_storage
    a,_,_=clients
    paper=session.get(Paper,'P1'); content=b'# Original paper\n\nSource evidence.'
    paper.raw_metadata={'zotero_fulltext':{'markdown_key':'raw/zotero/item/paper.md','markdown_sha256':hashlib.sha256(content).hexdigest()}}
    session.commit()
    monkeypatch.setattr(s3_storage,'get_file',lambda *args,**kw:content)
    assert a.get('/reading/papers/P1/markdown').json()=={'text':content.decode(),'source':'original'}
    assert 'attachment' in a.get('/reading/papers/P1/markdown?download=true').headers['content-disposition']
    monkeypatch.setattr(s3_storage,'get_file',lambda *args,**kw:b'wrong file')
    assert a.get('/reading/papers/P1/markdown').status_code==409
    paper.raw_metadata={};session.add(PaperSection(id='section1',paper_id='P1',section_type='methods',content='Measured result',order_index=0));session.commit()
    result=a.get('/reading/papers/P1/markdown').json()
    assert result['source']=='indexed_sections' and 'not the original Markdown' in result['text']


def test_shared_ai_turn_only_sees_group_history_and_fixed_papers(clients, monkeypatch):
    from app.services import paper_chat
    from types import SimpleNamespace
    a,b,_=clients;cid=new_chat(a)
    a.post(f'/chat/sessions/{cid}/comments',json={'query':'PRIVATE SECRET NOT SHARED'})
    msg=a.post(f'/chat/sessions/{cid}/comments',json={'query':'Shared method question'}).json()
    group=a.post(f'/chat/sessions/{cid}/share',json={'title':'Group','member_ids':['Bob'],'message_ids':[msg['id']]}).json()['id']
    calls=[]
    def rag(db, query, papers):
        calls.append(query)
        assert 'PRIVATE SECRET' not in query
        assert [paper.id for paper in papers] == ['P1']
        return []
    monkeypatch.setattr(paper_chat, 'search_paper_text', rag)
    assert b.post(f'/chat/sessions/{group}/messages',json={'query':'What about this method?','scope':{'paper_ids':['P2']}}).status_code==422
    response=b.post(f'/chat/sessions/{group}/messages',json={'query':'What about this method?'})
    assert response.status_code==200,response.text
    assert response.json()['user_message']['reader_id']=='Bob'
    assert len(calls)==1
