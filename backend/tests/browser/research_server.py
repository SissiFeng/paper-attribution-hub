"""Isolated browser fixture; only run via check_research_browser.py."""
import os,sys,time,secrets,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
TEST_DIR=Path(os.environ['PAS_BROWSER_TEST_DIR'])
os.environ['PAS_DATABASE_URL']='sqlite:///'+str(TEST_DIR/'test.db')
os.environ['PAS_ANTHROPIC_API_KEY']='';os.environ['PAS_KIMI_API_KEY']='';os.environ['PAS_LLM_PROVIDER']='auto'
os.environ['PAS_PUBLIC_URL']=os.environ['PAS_BROWSER_TEST_ORIGIN'];os.environ['PAS_SLACK_TEAM_ID']='T-UI'
sys.path.insert(0,str(ROOT/'backend'))
from app.db import Base,engine,SessionLocal
from app.models import all_models,Paper,PaperSection,PaperChunk
from app.models.reading import Reader,ReaderSession
from app.models.access import AdminGrant
from app.services.reader_auth import digest
from app.main import app as api
from starlette.applications import Starlette
from starlette.routing import Mount,Route
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
Base.metadata.create_all(engine)
identities=[]
with SessionLocal() as db:
 for rid,name in [('a','Researcher Alice'),('b','Researcher Bob'),('admin','Synthetic Administrator')]:
  token=secrets.token_urlsafe(32);identities.append({'id':rid,'token':token})
  if not db.get(Reader,rid):db.add(Reader(id=rid,workspace_id='T-UI',slack_user_id=rid,name=name,active=True));db.flush()
  db.add(ReaderSession(token_hash=digest(token),reader_id=rid,expires=int(time.time())+3600))
  if rid=='admin' and not db.get(AdminGrant,rid):db.add(AdminGrant(reader_id=rid))
 for pid,title,method,result in [
 ('P1','Robotic screening of nickel–iron oxygen evolution catalysts','NiFe catalyst was synthesized using robotic liquid handling in 1 M KOH at 25 °C.','An overpotential of 250 mV was measured at 10 mA cm−2. The short stability test remains a limitation.'),
 ('P2','Closed-loop catalyst discovery with Bayesian optimization','Bayesian optimization selected NiFe compositions. Experiments used 1 M KOH with a fixed catalyst loading.','An overpotential of 300 mV was measured at 100 mA cm−2. A baseline control was tested under identical conditions.')]:
  if not db.get(Paper,pid):
   db.add(Paper(id=pid,title=title,abstract=method+' '+result,doi='10.0000/'+pid,year=2026,venue='UI acceptance fixture',full_text_available=True));db.flush()
   for i,(kind,text) in enumerate([('methods',method),('results',result)]):
    sid=pid+'-'+kind;db.add(PaperSection(id=sid,paper_id=pid,section_type=kind,section_title=kind.title(),content=text,page_start=3+i,order_index=i));db.flush()
    db.add(PaperChunk(id=sid+'-chunk',paper_id=pid,section_id=sid,section_type=kind,chunk_text=text))
 db.commit()
p=TEST_DIR/'identities.json';p.touch(mode=0o600);p.write_text(json.dumps(identities))
async def entry(request):return FileResponse(ROOT/'frontend/dist-reading/reading.html')
async def main_entry(request):return FileResponse(ROOT/'frontend/dist/index.html')
async def fixture(request):return HTMLResponse('<h1>Local synthetic test identities</h1><p>Temporary SQLite database. No production accounts.</p>'+''.join('<form method="post" action="/fixture/login/'+u['id']+'"><button>Use synthetic '+u['id']+'</button></form>' for u in identities)+'<form method="post" action="/fixture/logout"><button>Clear test session</button></form>')
async def fixture_login(request):
 user=next(u for u in identities if u['id']==request.path_params['identity'])
 response=RedirectResponse('/',status_code=303)
 response.set_cookie('__Host-pas-reader',user['token'],secure=True,httponly=True,samesite='lax',path='/')
 return response
async def fixture_logout(request):
 response=RedirectResponse('/',status_code=303)
 response.delete_cookie('__Host-pas-reader',secure=True,httponly=True,samesite='lax',path='/')
 return response
app=Starlette(routes=[Mount('/api',api),Route('/fixture',fixture),Route('/fixture/login/{identity}',fixture_login,methods=['POST']),Route('/fixture/logout',fixture_logout,methods=['POST']),Route('/reading/',entry),Mount('/reading/assets',StaticFiles(directory=ROOT/'frontend/dist-reading/assets')),Mount('/assets',StaticFiles(directory=ROOT/'frontend/dist/assets')),Route('/{path:path}',main_entry)])
