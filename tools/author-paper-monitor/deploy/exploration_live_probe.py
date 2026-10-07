"""P2 HTTPS acceptance, including the deployed scheduler; remove all test records."""
import json
import os
import secrets
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, func, select
from app.db import SessionLocal
from app.models import Paper
from app.models.access import AccessAudit, AdminGrant
from app.models.exploration import (ResearchAlert, ResearchAlertReceipt, ResearchConnection,
    ResearchScreening, ResearchWatch)
from app.models.reading import Reader, ReaderSession
from app.models.research import ProjectMember, ProjectPaper, ResearchProject
from app.services.reader_auth import COOKIE, digest
from paper_monitor.exploration_smoke import exercise
from paper_monitor.research_smoke import real_papers


def main():
    ids=[]; clients=[]; tokens=[]; arrivals=[]; result=None
    public=os.environ['PAS_PUBLIC_URL']
    def arrival(phrase):
        pid='p2_live_paper_'+secrets.token_hex(12); arrivals.append(pid)
        with SessionLocal() as db:
            db.add(Paper(id=pid,title=phrase,source='openalex',created_at=datetime.now(UTC)))
            db.commit()
        return pid
    try:
        with SessionLocal() as db:
            for n in range(3):
                rid='p2_live_'+secrets.token_hex(12); token=secrets.token_urlsafe(32)
                ids.append(rid); tokens.append(token)
                db.add(Reader(id=rid,workspace_id=os.environ['PAS_SLACK_TEAM_ID'],slack_user_id=rid,
                    name='Temporary P2 verification '+str(n),active=True)); db.flush()
                db.add(ReaderSession(token_hash=digest(token),reader_id=rid,expires=int(time.time())+1800))
            db.add(AdminGrant(reader_id=ids[2])); papers=real_papers(db); db.commit()
        clients=[httpx.Client(base_url=public,headers={'Origin':public,'X-PAS-Request':'1'},
            cookies={COOKIE:t},timeout=45) for t in tokens]
        result=exercise(clients,ids,papers,prefix='/api',add_arrival=arrival)
        a=clients[0]
        project=a.post('/api/research/projects',json={'title':'Temporary deployed scheduler check','member_ids':[]})
        assert project.status_code==201,project.text
        path='/api/research/projects/'+project.json()['id']+'/exploration'
        phrase='p2-scheduler-'+secrets.token_hex(10)
        response=a.put(path+'/watch',json={'terms':[phrase],'criteria':'Temporary verification','enabled':True,'version':0})
        assert response.status_code==200,response.text
        pid=arrival(phrase); started=time.monotonic()
        print(json.dumps({'exploration_https':'passed',**result,'scheduler':'waiting for deployed service; no manual check'}),flush=True)
        # Read-only polling. The production process must create this alert itself.
        while time.monotonic()-started<1020:
            r=a.get(path); assert r.status_code==200,r.text
            if any(item['paper']['id']==pid for item in r.json()['alerts']):
                result['deployed_scheduler_seconds']=round(time.monotonic()-started)
                break
            time.sleep(15)
        else:
            raise AssertionError('Deployed scheduler did not discover the test arrival within 17 minutes')
        with httpx.Client(base_url=public,timeout=45) as anon:
            assert anon.get(path).status_code==401
        assert clients[2].get(path).status_code==404
    finally:
        for client in clients: client.close()
        with SessionLocal() as db:
            projects=list(db.scalars(select(ResearchProject.id).where(ResearchProject.owner_id.in_(ids))))
            for model in (ResearchAlertReceipt,ResearchAlert,ResearchScreening,ResearchConnection,ResearchWatch,
                          ProjectPaper,ProjectMember):
                db.execute(delete(model).where(model.project_id.in_(projects)))
            db.execute(delete(ResearchProject).where(ResearchProject.id.in_(projects)))
            for model in (ReaderSession,AdminGrant):
                db.execute(delete(model).where(model.reader_id.in_(ids)))
            db.execute(delete(AccessAudit).where(AccessAudit.actor_id.in_(ids)))
            db.execute(delete(Reader).where(Reader.id.in_(ids)))
            db.execute(delete(Paper).where(Paper.id.in_(arrivals))); db.commit()
            assert db.scalar(select(func.count()).select_from(Reader).where(Reader.id.in_(ids)))==0
            assert db.scalar(select(func.count()).select_from(Paper).where(Paper.id.in_(arrivals)))==0
        print(json.dumps({'exploration_live_cleanup':'passed','synthetic_identities':len(ids),'synthetic_papers':len(arrivals)}),flush=True)
    print(json.dumps({'exploration_live':'passed',**result}),flush=True)


main()
