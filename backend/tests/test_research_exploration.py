from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from app.models import Paper, PaperReference, PaperSection
from app.models.access import AdminGrant
from app.models.exploration import ResearchAlert, ResearchWatch
from app.models.reading import Reader
from tests.test_private_reading import clients, signed_client  # noqa: F401
from tests.test_research_workspace import project, source_anchor


@pytest.fixture
def setup(clients, session):
    a, b, admin = clients
    session.add(AdminGrant(reader_id='Carol'))
    for pid in ['P1', 'P2']:
        p = session.get(Paper, pid); p.source='openalex'; p.provenance='openalex'
        p.abstract='We discuss Bayesian optimization for catalyst discovery.'
    session.add(PaperSection(id='S1',paper_id='P1',section_type='methods',content='We use Bayesian optimization to select a NiFe catalyst.'))
    session.add(PaperReference(id='ref',citing_paper_id='P1',cited_paper_id='P2',raw_text='Another paper (2026).'))
    session.add(Paper(id='public',title='Bayesian optimization for catalysts',source='openalex'))
    session.add(Paper(id='private',title='Bayesian optimization secret draft',doi='10.1234/private',provenance='manual_upload'))
    session.commit()
    pid=project(a,['Bob'])
    return a,b,admin,pid,'/research/projects/'+pid+'/exploration'


def test_map_distinguishes_sources_hypotheses_and_never_leaks_notes(setup,session):
    a,b,_,pid,url=setup
    a.put('/reading/saved/P1',json={'note':'SECRET PRIVATE NOTE'})
    anchor=source_anchor(a)
    r=a.post(url+'/connections',json={'source_id':'P1','target_id':'P2','relation':'method_transfer',
        'rationale':'A transfer worth testing','evidence':[anchor|{'paper_id':'P1'}]})
    assert r.status_code==201,r.text
    data=b.get(url);assert data.status_code==200,data.text
    assert 'SECRET PRIVATE NOTE' not in data.text
    edges=data.json()['map']['edges']
    assert {e['kind'] for e in edges}=={'citation','method_mention','hypothesis'}
    assert len([e for e in edges if e['kind']=='method_mention'])==2
    for edge in edges:
        for anchor in edge['evidence']:
            source=b.get('/reading/papers/'+anchor['paper_id']+'/sources/'+anchor['kind']+'/'+anchor['source_id']).json()
            assert source['text'][anchor['start']:anchor['end']]==anchor['quote']
    assert b.delete(url+'/connections/'+r.json()['id']).status_code==403
    assert a.delete(url+'/connections/'+r.json()['id']).status_code==200


def test_related_is_labelled_bounded_public_and_literal(setup):
    a,_,_,_,url=setup
    response=a.get(url+'/related',params={'q':'Bayesian optimization'})
    assert response.status_code==200,response.text
    assert [v['paper']['id'] for v in response.json()['items']]==['public']
    assert 'not semantic relevance' in response.json()['basis']
    assert a.get(url+'/related',params={'q':'%%%'}).json()['items']==[]
    assert a.get(url+'/related',params={'q':'ab'}).status_code==422


def test_screening_preserves_each_reviewer_and_conflicts(setup):
    a,b,_,_,url=setup
    assert a.put(url+'/screening/public',json={'decision':'include','reason':'','version':0}).status_code==422
    assert a.put(url+'/screening/private',json={'decision':'include','reason':'steal','version':0}).status_code==404
    for client,decision in [(a,'include'),(b,'exclude')]:
        r=client.put(url+'/screening/public',json={'decision':decision,'reason':'Different research criteria','version':0})
        assert r.status_code==200,r.text
    assert a.put(url+'/screening/public',json={'decision':'exclude','reason':'stale overwrite','version':0}).status_code==409
    data=a.get(url).json()['screenings']
    assert {(r['reader_id'],r['decision']) for r in data}=={('Alice','include'),('Bob','exclude')}


def test_alert_baseline_duplicates_late_commit_and_personal_seen(setup,session):
    a,b,_,pid,url=setup
    payload={'terms':['Bayesian optimization'],'criteria':'Methods, not reviews','enabled':True,'version':0}
    assert b.put(url+'/watch',json=payload).status_code==403
    assert a.put(url+'/watch',json=payload).status_code==200
    assert a.put(url+'/watch',json=payload).status_code==409
    assert a.post(url+'/check').json()['new_alerts']==0  # No historical flood.
    session.add(Paper(id='new',title='Bayesian optimization new paper',source='openalex'))
    session.add(Paper(id='new-private',title='Bayesian optimization confidential',provenance='manual_upload'))
    session.commit()
    assert a.post(url+'/check').json()['new_alerts']==1
    assert b.post(url+'/check').json()['new_alerts']==0
    assert a.post(url+'/alerts/new/seen').status_code==200
    assert a.get(url).json()['alerts'][0]['seen'] is True
    assert b.get(url).json()['alerts'][0]['seen'] is False
    # Inserted after a prior scan but with an earlier creation timestamp.
    session.expire_all();since=session.get(ResearchWatch,pid).since
    session.add(Paper(id='late',title='Bayesian optimization late commit',source='openalex',created_at=since+timedelta(microseconds=1)))
    session.commit()
    assert a.post(url+'/check').json()['new_alerts']==1
    payload['version']=1;payload['enabled']=False
    assert a.put(url+'/watch',json=payload).status_code==200
    session.add(Paper(id='paused',title='Bayesian optimization paused',source='openalex'));session.commit()
    assert a.post(url+'/check').json()['new_alerts']==0


def test_all_routes_deny_nonmembers_admin_other_workspace_and_revoked(setup,session):
    from app.main import app
    a,b,admin,pid,url=setup
    outsider=signed_client(session,'Other','T2')
    assert TestClient(app).get(url).status_code==401
    a.put('/research/projects/'+pid+'/members',json={'member_ids':[]})
    for client in (b,admin,outsider):
        for method,path,payload in [('get',url,None),('get',url+'/related?q=catalyst',None),
            ('post',url+'/check',None),('put',url+'/watch',{'terms':['catalyst'],'criteria':'x','enabled':True,'version':0}),
            ('post',url+'/alerts/public/seen',None),('put',url+'/screening/public',{'decision':'include','reason':'x','version':0}),
            ('post',url+'/connections',{'source_id':'P1','target_id':'P2','relation':'contrasts','rationale':'x'}),
            ('delete',url+'/connections/unknown',None)]:
            r=getattr(client,method)(path,**({'json':payload} if payload else {}))
            assert r.status_code==(401 if client is outsider else 404),(path,r.text)


def test_connection_rejects_forged_source_and_outside_project(setup):
    a,_,_,_,url=setup
    body={'source_id':'P1','target_id':'public','relation':'complements','rationale':'x'}
    assert a.post(url+'/connections',json=body).status_code==422
    body['target_id']='P2';body['evidence']=[source_anchor(a)|{'paper_id':'P1','quote':'forged'}]
    assert a.post(url+'/connections',json=body).status_code==422
    body['evidence'][0]['version']='0'*64
    assert a.post(url+'/connections',json=body).status_code==409


def test_background_worker_runs_and_skips_disabled_owner(setup,session):
    from app.services.exploration_worker import refresh_watches
    a,_,_,pid,url=setup
    a.put(url+'/watch',json={'terms':['catalyst'],'criteria':'','enabled':True,'version':0})
    session.add(Paper(id='bg',title='New catalyst paper',source='openalex'));session.commit()
    refresh_watches();refresh_watches();session.expire_all()
    assert len(list(session.scalars(select(ResearchAlert).where(ResearchAlert.project_id==pid))))==1
    session.get(Reader,'Alice').active=False
    session.add(Paper(id='bg2',title='New catalyst paper two',source='openalex'));session.commit()
    refresh_watches();session.expire_all()
    assert session.get(ResearchAlert,(pid,'bg2')) is None


def test_additive_schema_idempotent_and_rejects_partial():
    from app.db import Base
    from app.services.exploration_schema import adopt_exploration_schema,NAMES
    e=create_engine('sqlite://')
    with e.begin() as conn:
        adopt_exploration_schema(conn,Base.metadata);adopt_exploration_schema(conn,Base.metadata)
        assert set(NAMES)<=set(inspect(conn).get_table_names())
        Base.metadata.tables[NAMES[-1]].drop(conn)
        with pytest.raises(RuntimeError,match='Partial'):
            adopt_exploration_schema(conn,Base.metadata)


def test_worker_lifespan_starts_and_stops_cleanly(monkeypatch):
    import asyncio
    from fastapi import FastAPI
    from app.services import exploration_worker as worker
    async def verify():
        ran=asyncio.Event(); loop=asyncio.get_running_loop()
        monkeypatch.setenv('PAS_EXPLORATION_WORKER','1')
        monkeypatch.setattr(worker,'refresh_watches',lambda:loop.call_soon_threadsafe(ran.set))
        app=FastAPI(); worker.install_worker(app)
        before=set(asyncio.all_tasks())
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(ran.wait(),2)
        assert set(asyncio.all_tasks())==before
        monkeypatch.setenv('PAS_EXPLORATION_WORKER','0');ran.clear()
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)
            assert not ran.is_set()
    asyncio.run(verify())
