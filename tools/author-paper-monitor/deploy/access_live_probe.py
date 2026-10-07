"""Live HTTPS/origin acceptance; synthetic identities are removed in finally."""
import json,os,secrets,time,re
import httpx
from sqlalchemy import select,delete,func
from app.db import SessionLocal
from app.models import ChatMessage,ChatSession
from app.models.reading import Reader,ReaderSession,ChatParticipant,Bookmark
from app.models.access import AdminGrant,AccessAudit
from app.services.reader_auth import COOKIE,digest


def main():
    public=os.environ['PAS_PUBLIC_URL'];team=os.environ['PAS_SLACK_TEAM_ID']
    alb='http://paper-attribution-dev-alb-918442769.ca-central-1.elb.amazonaws.com'
    ids=[];tokens=[];checks=[]
    def check(client,url,status,**kwargs):
        with client.stream(kwargs.pop('method','GET'),url,**kwargs) as response:
            assert response.status_code==status, (url.split('?')[0],response.status_code,status)
            if '/api/' in url and status in (200,401,403):assert 'no-store' in response.headers.get('cache-control',''),url
            checks.append({'path':url.replace(public,'cloudfront:').replace(alb,'origin:'),'status':status})
            return response.read()
    try:
        with SessionLocal() as db:
            for n in range(3):
                rid='p0_live_'+secrets.token_hex(12);token=secrets.token_urlsafe(32);ids.append(rid);tokens.append(token)
                db.add(Reader(id=rid,workspace_id=team,slack_user_id=rid,name='Temporary access verification '+str(n),active=True));db.flush()
                db.add(ReaderSession(token_hash=digest(token),reader_id=rid,expires=int(time.time())+900))
            db.add(AdminGrant(reader_id=ids[0]));db.commit()
        clients=[httpx.Client(headers={'Origin':public,'X-PAS-Request':'1'},cookies={COOKIE:token},follow_redirects=True,timeout=45) for token in tokens]
        a,b,c=clients;anon=httpx.Client(follow_redirects=True,timeout=45)
        for base in [public+'/api',alb]:
            for client,status in [(anon,401),(b,403),(a,200)]:
                check(client,base+'/access/check-admin',status)
                check(client,base+'/papers?limit=1',status)
                for path in ['/institution-authorship/options','/institution-authorship/report?limit=1','/institution-authorship/export.csv?limit=1']:
                    check(client,base+path,status)
        paths=['/tier1-tier2-openalex-institution-comparison.html','/data/tier1-tier2-openalex-institution-data.js','/assets/index-DoWr2ZMF.js']
        for path in paths:
            for client,status in [(anon,401),(b,403),(a,200)]:check(client,public+path,status)
        check(anon,public+'/protected-legacy/index.html',404)
        check(anon,'https://paper-attribution-frontend-dev-247893369214.s3.ca-central-1.amazonaws.com/protected-legacy/index.html',403)
        for client in [a,b,c]:check(client,public+'/api/reading/papers',200)
        created=json.loads(check(b,public+'/api/chat/sessions',201,method='POST',json={'title':'Temporary private verification'}))
        check(a,public+'/api/chat/sessions/'+created['id'],404)
        check(a,public+'/api/access/members/'+ids[1],200,method='PUT',json={'admin':True,'active':True})
        check(b,public+'/api/institution-authorship/options',200)
        check(a,public+'/api/access/members/'+ids[1],200,method='PUT',json={'admin':False,'active':True})
        check(b,public+'/api/institution-authorship/options',403)
        check(b,public+paths[0],403)
        check(a,public+'/api/access/members/'+ids[1],200,method='PUT',json={'admin':False,'active':False})
        check(b,public+'/api/reading/papers',401)
        for client in [a,b,c,anon]:client.close()
    finally:
        with SessionLocal() as db:
            chats=list(db.scalars(select(ChatSession.id).where(ChatSession.owner_id.in_(ids))))
            db.execute(delete(ChatParticipant).where(ChatParticipant.session_id.in_(chats)))
            db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(chats)))
            db.execute(delete(ChatSession).where(ChatSession.id.in_(chats)))
            db.execute(delete(Bookmark).where(Bookmark.reader_id.in_(ids)))
            db.execute(delete(ReaderSession).where(ReaderSession.reader_id.in_(ids)))
            db.execute(delete(AdminGrant).where(AdminGrant.reader_id.in_(ids)))
            db.execute(delete(AccessAudit).where(AccessAudit.actor_id.in_(ids)))
            db.execute(delete(Reader).where(Reader.id.in_(ids)));db.commit()
            assert db.scalar(select(func.count()).select_from(Reader).where(Reader.id.in_(ids)))==0
        print(json.dumps({'live_cleanup':'passed','synthetic_identities':len(ids)}))
    print(json.dumps({'live_access':'passed','checks':checks,'total':len(checks)}))


main()
