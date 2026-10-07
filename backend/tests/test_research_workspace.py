import json
import pytest
from sqlalchemy import select
from app.models import Paper, PaperChunk, PaperSection, ChatMessage
from app.models.access import AdminGrant
from app.models.research import ProjectMember
from app.services import paper_chat
from tests.test_private_reading import clients, signed_client, new_chat  # noqa: F401


@pytest.fixture
def workspace(clients, session):  # noqa: F811
    text = '🙂 We used NiFe catalyst in 1 M KOH. The current density was 10 mA cm−2. The overpotential was 250 mV. A limitation is the short stability test.'
    session.add(PaperSection(id='S1', paper_id='P1', section_type='methods', section_title='Methods and results', content=text, page_start=3))
    session.add(PaperSection(id='S2', paper_id='P2', section_type='results', section_title='Results', content='The method used a control baseline. Current density was 100 mA cm−2 at 300 mV overpotential.'))
    session.add(PaperChunk(id='C1', paper_id='P1', section_id='S1', section_type='methods', chunk_text=text, indexed_text='INTERNAL SECRET ATTRIBUTION'))
    session.get(Paper, 'P2').abstract = 'An abstract describing material synthesis and uncertain results.'
    session.add(AdminGrant(reader_id='Carol'))
    session.commit()
    return clients


def source_anchor(a, quote='NiFe catalyst'):
    source = a.get('/reading/papers/P1/sources/section/S1').json()
    start = source['text'].index(quote)
    return {k: source[k] for k in ('kind', 'source_id', 'version')} | {'start': start, 'end': start+len(quote), 'quote': quote}


def project(a, members=None):
    result = a.post('/research/projects', json={'title':'OER research','question':'Compare conditions','member_ids':members or []})
    assert result.status_code == 201,result.text
    pid = result.json()['id']
    for paper in ['P1','P2']:
        assert a.put(f'/research/projects/{pid}/papers/{paper}').status_code == 200
    return pid


def note(a, project_id=None):
    r = a.post('/research/annotations',json={'paper_id':'P1','project_id':project_id,'anchor':source_anchor(a),'body':'Private hypothesis'})
    assert r.status_code==201,r.text
    return r.json()


def matrix(a, project_id=None):
    r = a.post('/research/comparisons',json={'paper_ids':['P1','P2'],'project_id':project_id,'dimensions':['Conditions','Results','nonexistentXYZ']})
    assert r.status_code==201,r.text
    return r.json()


def test_private_default_and_explicit_copy_does_not_leak(workspace):
    a,b,admin = workspace
    pid = project(a,['Bob'])
    a.put('/reading/saved/P1',json={'note':'NEVER SHARE MY BOOKMARK'})
    n = note(a);m = matrix(a)
    for client in [b,admin]:
        assert client.get('/research/annotations').json()==[]
        assert client.get('/research/comparisons/'+m['id']).status_code==404
        assert client.put('/research/annotations/'+n['id'],json={'body':'steal'}).status_code==404
        assert client.post('/research/annotations/'+n['id']+'/copy',json={'project_id':pid}).status_code==404
    assert 'NEVER SHARE' not in b.get('/research/projects/'+pid).text
    assert b.get('/research/annotations?project_id='+pid).json()==[]
    copy_n=a.post('/research/annotations/'+n['id']+'/copy',json={'project_id':pid})
    assert copy_n.status_code==201,copy_n.text
    copied=a.post('/research/comparisons/'+m['id']+'/copy',json={'project_id':pid}).json()
    assert b.get('/research/comparisons/'+copied['id']).status_code==200
    assert len(b.get('/research/annotations?project_id='+pid).json())==1
    assert len(a.get('/research/annotations').json())==1
    assert b.get('/research/comparisons/'+m['id']).status_code==404
    assert admin.get('/research/projects/'+pid).status_code==404


def test_anchor_integrity_cross_paper_and_unicode(workspace, session):
    a,_,_=workspace
    anchor=source_anchor(a)
    assert a.post('/research/annotations',json={'paper_id':'P1','anchor':anchor}).status_code==201
    assert a.get('/reading/papers/P2/sources/section/S1').status_code==404
    assert a.get('/reading/papers/P1/sources/raw/S1').status_code==404
    wrong={**anchor,'quote':'unsupported finding'}
    assert a.post('/research/annotations',json={'paper_id':'P1','anchor':wrong}).status_code==422
    wrong={**anchor,'start':anchor['start']+1,'end':anchor['end']+1}
    assert a.post('/research/annotations',json={'paper_id':'P1','anchor':wrong}).status_code==422
    session.get(PaperSection,'S1').content+=' Updated source.';session.commit()
    assert a.post('/research/annotations',json={'paper_id':'P1','anchor':anchor}).status_code==409


def test_comparison_units_provenance_missing_and_manual_interpretation(workspace):
    a,b,_=workspace;m=matrix(a)
    cells=m['cells'];assert len(cells)==6
    assert all(c['status']=='no_evidence_found' for c in cells if c['dimension']=='nonexistentXYZ')
    for c in cells:
        for e in c['evidence']:
            doc=a.get(f"/reading/papers/{c['paper_id']}/sources/{e['kind']}/{e['source_id']}").json()
            assert e['quote']==doc['text'][e['start']:e['end']]
    encoded=json.dumps(cells,ensure_ascii=False)
    assert '10 mA cm−2' in encoded and '100 mA cm−2' in encoded
    assert '250 mV' in encoded and '300 mV' in encoded
    assert all(c['interpretation']=='' for c in cells)
    cell=next(c for c in cells if c['paper_id']=='P1' and c['dimension']=='Conditions')
    payload={**cell,'interpretation':'Different current densities; these values cannot be directly ranked.'}
    assert b.put('/research/comparisons/'+m['id']+'/cells',json=payload).status_code==404
    r=a.put('/research/comparisons/'+m['id']+'/cells',json=payload)
    assert r.status_code==200,r.text
    assert any(c['status']=='reader_interpretation' for c in r.json()['cells'])
    assert a.put('/research/comparisons/'+m['id']+'/cells',json={**payload,'evidence':[]}).status_code==422
    manual={**payload,'dimension':'nonexistentXYZ','evidence':[source_anchor(a)]}
    assert a.put('/research/comparisons/'+m['id']+'/cells',json=manual).status_code==200


def test_project_membership_revoke_covers_creator_and_all_artifacts(workspace):
    a,b,admin=workspace;pid=project(a,['Bob'])
    n=note(b,pid);m=matrix(b,pid)
    chat=b.post(f'/research/projects/{pid}/discussions',json={'paper_ids':['P1'],'title':'Group evidence'}).json()['id']
    result=a.get('/chat/sessions/'+chat)
    assert result.status_code==200
    assert result.json()['owner_id'] is None  # Legacy P0 cannot re-grant access on rollback.
    assert b.post('/chat/sessions/'+chat+'/comments',json={'query':'shared comment'}).status_code==201
    assert b.put('/chat/sessions/'+chat+'/members',json={'member_ids':['Carol']}).status_code==403
    assert b.post('/chat/sessions/'+chat+'/share',json={'title':'escape','member_ids':['Carol']}).status_code==403
    assert b.put(f'/research/projects/{pid}/members',json={'member_ids':[]}).status_code==403
    assert a.put(f'/research/projects/{pid}/members',json={'member_ids':[]}).status_code==200
    for client in [b,admin]:
        for path in [f'/research/projects/{pid}',f'/research/comparisons/{m["id"]}',f'/research/annotations?project_id={pid}',f'/chat/sessions/{chat}',f'/chat/sessions/{chat}/members']:
            assert client.get(path).status_code==404,path
        assert client.post(f'/chat/sessions/{chat}/messages',json={'query':'method'}).status_code==404
        assert client.post(f'/chat/sessions/{chat}/messages/stream',json={'query':'method'}).status_code==404
        assert client.put('/research/annotations/'+n['id'],json={'body':'late'}).status_code==404
    assert b.get('/chat/sessions').json()==[]
    assert b.get('/research/projects').json()==[]
    assert b.get('/research/comparisons').json()==[]


def test_project_selected_message_copy_is_separate(workspace):
    a,b,_=workspace;pid=project(a,['Bob']);cid=new_chat(a)
    secret=a.post(f'/chat/sessions/{cid}/comments',json={'query':'DO NOT SHARE'}).json()
    chosen=a.post(f'/chat/sessions/{cid}/comments',json={'query':'Chosen comment'}).json()
    r=a.post(f'/research/projects/{pid}/discussions',json={'paper_ids':['P1'],'source_session_id':cid,'message_ids':[chosen['id']]})
    assert r.status_code==201,r.text
    copy_id=r.json()['id'];shared=b.get('/chat/sessions/'+copy_id).json()
    assert shared['project_id']==pid
    assert [m['content'] for m in shared['messages']]==['Chosen comment']
    assert shared['scope']['page_context'] is None
    assert secret['content'] not in json.dumps(shared)
    assert b.get('/chat/sessions/'+cid).status_code==404
    assert a.post(f'/research/projects/{pid}/discussions',json={'paper_ids':['P2'],'source_session_id':cid}).status_code==422


def test_project_validation_workspace_and_csrf(workspace, session):
    a,b,_=workspace;foreign=signed_client(session,'Foreign','T2')
    assert a.post('/research/projects',json={'title':'bad','member_ids':['Foreign']}).status_code==422
    assert a.post('/research/projects',json={'title':'  '}).status_code==422
    pid=project(a)
    assert b.put(f'/research/projects/{pid}/papers/P1').status_code==404
    assert foreign.get('/research/projects/'+pid).status_code==401
    assert a.post('/research/projects',json={'title':'bad'},headers={'Origin':'https://evil.test'}).status_code==403
    assert a.post('/research/comparisons',json={'paper_ids':['P1','P1']}).status_code==422
    assert a.post('/research/comparisons',json={'paper_ids':['P1','P2'],'dimensions':['']}).status_code==422
    assert a.get('/research/projects').headers['cache-control']=='no-store'


def test_generation_only_uses_published_evidence_and_rejects_bad_citations(workspace, monkeypatch):
    a,_,_=workspace;cid=new_chat(a);contexts=[]
    def generate(query,context,**kwargs):
        contexts.append(context);return 'A claim [1] and nonexistent [99].','test-model'
    monkeypatch.setattr(paper_chat,'generate_grounded_answer',generate)
    r=a.post('/chat/sessions/'+cid+'/messages',json={'query':'NiFe catalyst method'}).json()['assistant_message']
    assert contexts and all('INTERNAL SECRET' not in c for c in contexts)
    assert r['model']=='retrieval-only' and r['audit']['rejected_citations'] is True
    assert '[99]' not in r['content']
    assert r['sources'][0]['anchor']['kind']=='chunk'
    monkeypatch.setattr(paper_chat,'generate_grounded_answer',lambda *a,**kw:('NiFe catalyst was used [1].','test-model'))
    r=a.post('/chat/sessions/'+cid+'/messages',json={'query':'NiFe catalyst method'}).json()['assistant_message']
    assert r['model']=='test-model' and r['audit']['citation_check']=='references_only_not_entailment'


def test_revoked_project_member_cannot_receive_inflight_answer(workspace, session, monkeypatch):
    a,b,_=workspace;pid=project(a,['Bob'])
    cid=b.post(f'/research/projects/{pid}/discussions',json={'paper_ids':['P1']}).json()['id']
    def revoke_during_search(db, query, papers):
        member=db.get(ProjectMember,(pid,'Bob'));db.delete(member);db.flush()
        return []
    monkeypatch.setattr(paper_chat,'search_paper_text',revoke_during_search)
    r=b.post(f'/chat/sessions/{cid}/messages',json={'query':'NiFe catalyst method'})
    assert r.status_code==404,r.text
    session.expire_all()
    assert list(session.scalars(select(ChatMessage).where(ChatMessage.session_id==cid)))==[]


def test_model_status_has_no_secret_and_abstract_fallback(workspace, monkeypatch):
    a,_,_=workspace
    from app.config import settings
    monkeypatch.setattr(settings,'kimi_api_key','')
    monkeypatch.setattr(settings,'anthropic_api_key','')
    monkeypatch.setattr(settings,'llm_provider','auto')
    assert a.get('/reading/model').json()['mode']=='evidence_only'
    monkeypatch.setattr(settings,'anthropic_api_key','never-expose-this-key')
    result=a.get('/reading/model')
    assert result.json()['mode']=='generation_configured'
    assert 'never-expose' not in result.text and result.json()['health']=='not_checked'
    monkeypatch.setattr(settings,'anthropic_api_key','')
    # Paper with only an abstract still provides an explicitly labelled source.
    cid=a.post('/chat/sessions',json={'scope':{'paper_ids':['P2']}}).json()['id']
    reply=a.post(f'/chat/sessions/{cid}/messages',json={'query':'material synthesis'}).json()['assistant_message']
    assert any(s['section_type']=='abstract' for s in reply['sources'])
