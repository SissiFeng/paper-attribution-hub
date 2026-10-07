"""CloudFront P1 workflow using temporary identities; always remove their records."""
import json,os,secrets,time
import httpx
from sqlalchemy import select,delete,func
from app.db import SessionLocal
from app.models import ChatMessage,ChatSession
from app.models.reading import Reader,ReaderSession,ChatParticipant,Bookmark
from app.models.access import AdminGrant,AccessAudit
from app.models.research import (Annotation,EvidenceComparison,ProjectDiscussion,ProjectMember,ProjectPaper,ResearchProject)
from app.services.reader_auth import COOKIE,digest
from paper_monitor.research_smoke import exercise,real_papers


def main():
    ids=[];clients=[];tokens=[];public=os.environ['PAS_PUBLIC_URL'];result=None
    try:
        with SessionLocal() as db:
            for n in range(3):
                rid='p1_live_'+secrets.token_hex(12);token=secrets.token_urlsafe(32);ids.append(rid);tokens.append(token)
                db.add(Reader(id=rid,workspace_id=os.environ['PAS_SLACK_TEAM_ID'],slack_user_id=rid,name='Temporary P1 verification '+str(n),active=True));db.flush()
                db.add(ReaderSession(token_hash=digest(token),reader_id=rid,expires=int(time.time())+1800))
            db.add(AdminGrant(reader_id=ids[2]));papers=real_papers(db);db.commit()
        clients=[httpx.Client(base_url=public,headers={'Origin':public,'X-PAS-Request':'1'},cookies={COOKIE:t},timeout=45) for t in tokens]
        result=exercise(clients,ids,papers,prefix='/api')
        with httpx.Client(base_url=public,timeout=45) as anon:
            for path in ['/research/projects','/research/annotations','/research/comparisons','/reading/model']:
                assert anon.get('/api'+path).status_code==401,path
        # Confirm P0 default-deny and private records coexist with the new workflow.
        assert clients[0].get('/api/access/members').status_code==403
        assert clients[2].get('/api/access/members').status_code==200
    finally:
        for client in clients:client.close()
        with SessionLocal() as db:
            projects=list(db.scalars(select(ResearchProject.id).where(ResearchProject.owner_id.in_(ids))))
            chats=list(db.scalars(select(ChatSession.id).where(ChatSession.owner_id.in_(ids))))
            chats+=list(db.scalars(select(ProjectDiscussion.session_id).where(ProjectDiscussion.project_id.in_(projects))))
            db.execute(delete(ProjectDiscussion).where(ProjectDiscussion.project_id.in_(projects)))
            db.execute(delete(Annotation).where(Annotation.owner_id.in_(ids)))
            db.execute(delete(EvidenceComparison).where(EvidenceComparison.owner_id.in_(ids)))
            db.execute(delete(ProjectPaper).where(ProjectPaper.project_id.in_(projects)))
            db.execute(delete(ProjectMember).where(ProjectMember.project_id.in_(projects)))
            db.execute(delete(ResearchProject).where(ResearchProject.id.in_(projects)))
            db.execute(delete(ChatParticipant).where(ChatParticipant.session_id.in_(chats)))
            db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(chats)))
            db.execute(delete(ChatSession).where(ChatSession.id.in_(chats)))
            db.execute(delete(Bookmark).where(Bookmark.reader_id.in_(ids)))
            db.execute(delete(ReaderSession).where(ReaderSession.reader_id.in_(ids)))
            db.execute(delete(AdminGrant).where(AdminGrant.reader_id.in_(ids)))
            db.execute(delete(AccessAudit).where(AccessAudit.actor_id.in_(ids)))
            db.execute(delete(Reader).where(Reader.id.in_(ids)));db.commit()
            assert db.scalar(select(func.count()).select_from(Reader).where(Reader.id.in_(ids)))==0
        print(json.dumps({'research_live_cleanup':'passed','synthetic_identities':len(ids)}))
    print(json.dumps({'research_live':'passed',**result,'additional_gate_checks':6}))


main()
