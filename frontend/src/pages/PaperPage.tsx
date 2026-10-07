import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { usePasAccount, RequireAccount } from '@/components/PasAccount';
import { api } from '@/reading/api';
import type { Paper } from '@/reading/api';
import '@/paper-pages.css';
import PaperReviewPage from './PaperReviewPage';
import { EvidencePanel } from '@/components/EvidencePanel';
import { getPublicPaper } from '@/lib/api';
import type { Paper as SharedPaper } from '@/types';

export const paperUrl=(id:string)=>'/papers/'+encodeURIComponent(id);

export function PaperCatalogue() {
  const [params]=useSearchParams(), navigate=useNavigate();
  const [error,setError]=useState('');
  const doi=params.get('doi');
  useEffect(()=>{
    let active=true;setError('');
    if(doi)api<{id:string}>('/catalog/resolve?'+new URLSearchParams({doi})).then(p=>{if(active)navigate(paperUrl(p.id),{replace:true});}).catch(e=>{if(active)setError(e.message);});
    return()=>{active=false;};
  },[doi,navigate]);
  if(doi)return <section className="pas-paper-panel"><p role={error?'alert':'status'}>{error||'Finding this paper…'}</p><Link to="/papers">Browse all papers</Link></section>;
  return <PaperReviewPage readOnly/>;
}

export default function PaperPage(){
  const {paperId=''}=useParams(), {user,signIn}=usePasAccount();
  const [publicPaper,setPaper]=useState<SharedPaper|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(true);
  const [personal,setPersonal]=useState<Paper|null>(null),[markdown,setMarkdown]=useState(''),[notice,setNotice]=useState('');
  const paper=publicPaper || (user && personal ? {...personal,authors:personal.authors.map(name=>({name,order:0,affiliation:null})),keywords:[],provenance:'reading'} : null);
  useEffect(()=>{let active=true;setPaper(null);setError('');setBusy(true);getPublicPaper(paperId).then(p=>{if(active)setPaper(p);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setBusy(false);});return()=>{active=false;};},[paperId]);
  useEffect(()=>{let active=true;setPersonal(null);setMarkdown('');setNotice('');if(user)api<Paper>('/reading/papers/'+encodeURIComponent(paperId)).then(p=>{if(active)setPersonal(p);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[paperId,user?.id]);
  const privateAction=(action:()=>Promise<void>)=>{if(!user){signIn();return;}action().catch(e=>setError(e.message));};
  async function save(){await api('/reading/saved/'+encodeURIComponent(paperId),{note:personal?.note||''},'PUT');setPersonal(p=>p?{...p,saved:true}:p);setNotice('Saved to your private reading list.');}
  async function readMarkdown(){const r=await api<{text:string}>('/reading/papers/'+encodeURIComponent(paperId)+'/markdown');setMarkdown(r.text);}
  if(busy)return <p role="status">Loading this paper…</p>;
  if(!paper)return <section className="pas-paper-panel"><h1>Paper unavailable</h1><p role="alert">{error||'This paper could not be found.'}</p><Link to="/">Browse PAS papers</Link></section>;
  const research='/research?'+new URLSearchParams({paper:paper.id});
  return <article className="pas-paper-detail"><Link to="/papers">← Papers</Link><div className="pas-paper-meta">{paper.year||'Date unavailable'} · {paper.venue||'Publication'}</div><h1>{paper.title}</h1><p className="pas-paper-authors">{paper.authors.map(author=>author.name).join(', ')}</p>
    <div className="pas-keywords">{(paper.keywords||[]).slice(0,8).map(k=><span key={k}>{k}</span>)}</div>
    <div className="pas-paper-actions"><button disabled={Boolean(user && !personal)} onClick={()=>privateAction(save)}>{personal?.saved?'Saved privately':'Save paper'}</button><Link to={research}>Ask, annotate & compare</Link>{paper.doi && <a href={'https://doi.org/'+encodeURI(paper.doi)} target="_blank" rel="noreferrer">Publisher ↗</a>}</div>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    <section className="pas-paper-panel"><EvidencePanel key={paper.id} paper={paper} readOnly/></section>
    <section className="pas-paper-panel"><h2>Full text & Markdown</h2><p>{paper.full_text_available?(user?'Read the source text below or open the research tools to annotate passages.':'Source text is available in PAS. Sign in to read it and keep your annotations private.'):'The publication is in PAS; full text has not been acquired yet. The abstract and publisher link remain available.'}</p>
      {(paper.full_text_available || personal?.markdown_status && personal.markdown_status!=='unavailable') && <div className="pas-paper-actions"><button onClick={()=>privateAction(readMarkdown)}>Read Markdown</button>{user && <a href={'/api/reading/papers/'+encodeURIComponent(paperId)+'/markdown?download=true'}>Download .md</a>}</div>}
      {user && markdown && <pre className="pas-markdown">{markdown}</pre>}
    </section>
    <section className="pas-paper-panel"><h2>Continue your research</h2><p>Use evidence-linked answers, passage annotations, paper comparisons and project folders in your PAS workspace.</p><Link to={research}>Open research tools for this paper →</Link><p className="pas-privacy-note">Your notes and conversations are private. Sharing requires selecting the people and content explicitly.</p></section>
  </article>;
}

export function ResearchWorkspace(){
  const [params]=useSearchParams(),{user}=usePasAccount();
  const query=new URLSearchParams(params);query.set('embedded','1');
  return <RequireAccount><div className="pas-research-workspace"><h1>My research</h1><iframe key={user?.id} title="PAS private research workspace" src={'/reading/?'+query.toString()}/></div></RequireAccount>;
}
