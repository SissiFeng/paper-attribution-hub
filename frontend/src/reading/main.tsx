import React, { useEffect, useRef, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { api, identityChanged, safeLink } from './api';
import type { Discussion, Message, Paper, Reader } from './api';
import './reading.css';
import { AccessManagement } from './AccessManagement';
import { EvidenceReader } from './EvidenceReader';
import { EvidenceComparison } from './EvidenceComparison';
import { Projects } from './Projects';
import type { Anchor, Comparison, Project } from './api';
import { navigationShortcut } from '../components/navigation';

const params = () => new URLSearchParams(location.search);
function linkTo(kind: 'paper' | 'discussion' | 'project' | 'comparison', id: string) { return location.origin + (kind==='paper' ? '/papers/'+encodeURIComponent(id) : '/research?' + new URLSearchParams({ [kind]: id })); }
function workspaceLink(kind: 'paper' | 'discussion' | 'project' | 'comparison', id: string) { return location.origin + '/reading/?' + new URLSearchParams({ [kind]: id, embedded:'1' }); }
function sourceText(message: Message) { return message.answer_kind === 'verified_structured' ? 'Verified catalogue query' : message.answer_kind === 'evidence_grounded' ? 'Answer with source citations · check the cited passages' : 'Limited evidence · read the passages before drawing conclusions'; }
function Text({ value }: { value: string }) {
  // React escapes all source content. Raw HTML in PDFs/Markdown is never executed.
  return <div className="document">{value.split(/\n\s*\n/).map((part, i) => /^#{1,3}\s/.test(part) ? <h3 key={i}>{part.replace(/^#{1,3}\s/, '')}</h3> : <p key={i}>{part}</p>)}</div>;
}
function App() {
  const [embedded] = useState(() => params().get('embedded') === '1');
  useEffect(()=>{
    if(!embedded||window.parent===window)return;
    const key=(event:KeyboardEvent)=>{
      if(navigationShortcut(event)&&!document.querySelector('dialog[open], [aria-modal="true"]')){
        event.preventDefault();window.parent.postMessage({type:'pas:navigation:open'},window.location.origin);
      }
    };
    window.addEventListener('keydown',key);
    return()=>window.removeEventListener('keydown',key);
  },[embedded]);
  useEffect(() => {
    if (embedded) return;
    const query=params(),paper=query.get('paper'),doi=query.get('doi');
    const returnTo=query.get('return_to');
    if(paper) location.replace('/papers/'+encodeURIComponent(paper));
    else if(doi) location.replace('/papers?'+new URLSearchParams({doi}));
    else if(returnTo?.startsWith('/') && !returnTo.startsWith('//') && !returnTo.includes('\\') && !returnTo.startsWith('/reading')) location.replace(returnTo);
    else if(['discussion','project','comparison','manage'].some(key=>query.has(key))) location.replace('/research?'+query.toString());
    else location.replace('/');
  }, [embedded]);
  const [user, setUser] = useState<Reader | null>(null), [checking, setChecking] = useState(true);
  const [pair, setPair] = useState<{ command: string; slack_url: string; expires_at: number } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const refresh = () => { setUser(null); setChecking(true); api<Reader>('/auth/me').then(setUser).catch(() => setUser(null)).finally(() => setChecking(false)); };
    const lost = () => { setUser(null); setChecking(false); setPair(null); };
    const changed = (event: StorageEvent) => { if (event.key === 'pas.identity.changed') refresh(); };
    refresh(); window.addEventListener('storage', changed); window.addEventListener('pas-auth-lost', lost);
    return () => { window.removeEventListener('storage', changed); window.removeEventListener('pas-auth-lost', lost); };
  }, []);
  useEffect(() => {
    // Anonymous pairing has no session yet. A normal 401 must not cancel it
    // while the reader switches to Slack or waits for confirmation.
    if (!user) return;
    let active = true;
    const focus = () => { api<Reader>('/auth/me').then(value => { if (active) setUser(value); }).catch(() => { if (active) setUser(null); }); };
    const timer = window.setInterval(focus, 60000);
    window.addEventListener('focus', focus);
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', focus); };
  }, [user?.id]);
  useEffect(() => {
    if (!pair) return;
    let active = true, busy = false;
    const timer = window.setInterval(async () => {
      if (busy) return; busy = true;
      try {
        const result = await api<{ status: string; user?: Reader }>('/auth/connect/complete', {});
        if (active && result.user) { identityChanged(); setUser(result.user); setPair(null); }
      } catch (e) { if (active) { setError((e as Error).message); setPair(null); } }
      finally { busy = false; }
    }, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [pair]);
  useEffect(() => {
    const target = params().get('return_to');
    if (user?.role === 'admin' && target?.startsWith('/') && !target.startsWith('//') && !target.includes('\\')) location.replace(target);
  }, [user]);
  async function login() { if (connecting) return; setConnecting(true); setError(''); try { setPair(await api('/auth/connect', {})); } catch (e) { setError((e as Error).message); } finally { setConnecting(false); } }
  async function logout() { try { await api('/auth/logout', {}); identityChanged(); setUser(null); setPair(null); } catch (e) { setError((e as Error).message); } }
  return <div className={embedded?'embedded-research':''}>{!embedded && <header className="masthead"><a href="/" className="wordmark">PAS <span>READING ROOM</span></a><div>{user && <><span>{user.name}</span>{user.role === 'admin' && <><a href="/">Analytics</a><a href="/research?manage=members">Access</a></>}<button onClick={logout}>Sign out</button></>}</div></header>}
    {user ? (user.role === 'admin' && params().get('manage') === 'members' ? <AccessManagement user={user}/> : <ReadingSpace key={user.id + user.role} user={user}/>) : <main className="welcome"><span className="eyebrow">FROM DISCOVERY TO DISCUSSION</span><h1>A place to read,<br/>think, and compare.</h1><p>Open a paper from Slack. Keep your questions and notes private, then choose what to bring to a small reading group.</p>
      {checking ? <p role="status">Checking your session…</p> : pair ? <div className="login-card"><h2>Confirm in your AC Papers private chat</h2><p>Copy this command and send it to the bot. Keep this browser tab open; it will sign you in automatically.</p><code>{pair.command}</code><div className="actions"><button onClick={() => navigator.clipboard.writeText(pair.command).catch(() => setError('Select and copy the command above.'))}>Copy command</button><a className="button primary" href={pair.slack_url} target="_blank" rel="noreferrer">Open Slack ↗</a></div><small>Expires in five minutes. Only confirm a code from your own PAS browser tab.</small><p role="status">Waiting for your confirmation…</p></div> : <><p>Sign in with your Slack account to open the library. You will confirm a one-time command in your private chat with AC Papers.</p><button className="primary large" disabled={connecting} onClick={login}>{connecting ? 'Connecting…' : 'Connect with AC Papers'}</button></>}
      {error && <p className="error" role="alert">{error}</p>}<div className="privacy-line">Your notes and conversations start private. Shared discussions are available only to the members you select.</div></main>}
  </div>;
}
function ReadingSpace({ user }: { user: Reader }) {
  const [papers, setPapers] = useState<Paper[]>([]), [paper, setPaper] = useState<Paper | null>(null);
  const [q, setQ] = useState(''), [search, setSearch] = useState(''), [savedOnly, setSavedOnly] = useState(false), [offset, setOffset] = useState(0), [more, setMore] = useState(false);
  const [selected, setSelected] = useState<string[]>([]), [comparison, setComparison] = useState<Comparison | null>(null);
  const [dimensions, setDimensions] = useState('Materials, Methods, Conditions, Baselines, Results, Limitations');
  const [projects, setProjects] = useState<Project[]>([]), [projectId, setProjectId] = useState<string | null>(params().get('project')), [showProjects, setShowProjects] = useState(params().has('project'));
  const [myComparisons, setMyComparisons] = useState<Comparison[]>([]), [copyProject, setCopyProject] = useState('');
  const [source, setSource] = useState<{paper_id:string;kind:string;source_id:string;anchor?:Anchor} | null>(null);
  const [modelStatus, setModelStatus] = useState('Checking answer mode…');
  const loadProjects = () => api<Project[]>('/research/projects').then(setProjects);
  const loadComparisons = () => api<Comparison[]>('/research/comparisons').then(setMyComparisons);
  const locate = (anchor: Anchor) => setSource({ ...anchor, anchor });
  function selectProject(id: string) { setProjectId(id); setShowProjects(true); setPaper(null); setChat(null); setComparison(null); window.history.replaceState(null, '', workspaceLink('project', id)); }
  function showComparison(c: Comparison) { setComparison(c); setShowProjects(false); setPaper(null); setChat(null); window.history.replaceState(null, '', workspaceLink('comparison', c.id)); }
  const [chats, setChats] = useState<Discussion[]>([]), [chat, setChat] = useState<Discussion | null>(null);
  const [members, setMembers] = useState<Reader[]>([]), [groupMembers, setGroupMembers] = useState<Reader[]>([]);
  const [question, setQuestion] = useState(''), [note, setNote] = useState(''), [markdown, setMarkdown] = useState('');
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const [sharing, setSharing] = useState<'copy' | 'members' | 'project' | null>(null), [invitees, setInvitees] = useState<string[]>([]), [chosenMessages, setChosenMessages] = useState<string[]>([]), [groupTitle, setGroupTitle] = useState('');
  const libraryRequest = useRef(0), paperRequest = useRef(0);
  const report = (e: unknown) => setError((e as Error).message);
  const history = () => api<Discussion[]>('/chat/sessions').then(setChats);
  const loadPapers = async () => { const version = ++libraryRequest.current; const r = await api<{ items: Paper[]; has_more: boolean }>('/reading/papers?' + new URLSearchParams({ q: search, saved: String(savedOnly), offset: String(offset) })); if (version === libraryRequest.current) { setPapers(r.items); setMore(r.has_more); } };
  async function openPaper(id: string, standalone = false) { const version = ++paperRequest.current; setError(''); setMarkdown(''); setComparison(null); setShowProjects(false); if (standalone) setChat(null); const p = await api<Paper>('/reading/papers/' + encodeURIComponent(id)); if (version !== paperRequest.current) return; setPaper(p); setNote(p.note); if (standalone || !chat) window.history.replaceState(null, '', workspaceLink('paper', id)); }
  async function openChat(id: string) { setShowProjects(false); setError(''); setSharing(null); const c = await api<Discussion>('/chat/sessions/' + encodeURIComponent(id)); setChat(c); setPaper(null); setComparison(null); setMarkdown(''); setGroupMembers(await api<Reader[]>('/chat/sessions/' + c.id + '/members')); window.history.replaceState(null, '', workspaceLink('discussion', id)); }
  useEffect(() => { loadPapers().catch(report); }, [savedOnly, offset, search]);
  useEffect(() => {
    history().catch(report); loadProjects().catch(report); loadComparisons().catch(report);
    api<{message:string}>('/reading/model').then(s => setModelStatus(s.message)).catch(report);
    const initial = params();
    if (initial.get('comparison')) api<Comparison>('/research/comparisons/' + initial.get('comparison')).then(showComparison).catch(report);
    else if (initial.get('discussion')) openChat(initial.get('discussion')!).catch(report);
    else if (initial.get('paper')) openPaper(initial.get('paper')!).catch(report);
    else if (initial.get('doi')) api<{ id: string }>('/reading/resolve?doi=' + encodeURIComponent(initial.get('doi')!)).then(r => openPaper(r.id)).catch(report);
  }, []);
  // Recheck shared access and refresh collaborators' comments; removed members lose the UI too.
  useEffect(() => {
    if (!chat?.shared || busy) return;
    const id = chat.id; let active = true;
    const timer = window.setInterval(() => {
      api<Discussion>('/chat/sessions/' + id).then(c => { if (active) setChat(c); }).catch(e => { if (active) { setChat(null); setGroupMembers([]); setError((e as Error).message); } });
    }, 12000);
    return () => { active = false; window.clearInterval(timer); };
  }, [chat?.id, chat?.shared, busy]);
  async function startChat(ids: string[]) {
    if (!ids.length) throw new Error('Open a paper or select papers for comparison first.');
    const c = await api<Discussion>('/chat/sessions', { title: ids.length > 1 ? 'Paper comparison' : paper?.title.slice(0,160) || 'Paper discussion', scope: { paper_ids: ids } });
    setChat(c); setPaper(null); setComparison(null); setMarkdown(''); setGroupMembers([user]); setQuestion(''); await history(); window.history.replaceState(null, '', workspaceLink('discussion', c.id)); return c;
  }
  async function ask(comment = false) {
    if (!question.trim() || busy) return; setBusy(true); setError('');
    try { const c = chat || await startChat(comparison ? comparison.paper_ids : paper ? [paper.id] : []);
      await api('/chat/sessions/' + c.id + (comment ? '/comments' : '/messages'), { query: question });
      setQuestion(''); await openChat(c.id); await history();
    } catch(e) { report(e); } finally { setBusy(false); }
  }
  async function savePaper() {
    if (!paper) return; try { await api('/reading/saved/' + encodeURIComponent(paper.id), { note }, 'PUT'); setPaper({ ...paper, saved: true, note }); setNotice('Saved to your private reading list.'); await loadPapers(); } catch(e) { report(e); }
  }
  async function compare() { setError(''); try { const c = await api<Comparison>('/research/comparisons', { paper_ids: selected, dimensions: dimensions.split(',').map(d => d.trim()).filter(Boolean) }); showComparison(c); await loadComparisons(); } catch(e) { report(e); } }
  async function share(mode: 'copy' | 'members' | 'project') {
    setError(''); try { const available = await api<Reader[]>('/chat/members'); setMembers(available); setInvitees(mode === 'members' ? groupMembers.filter(m => m.id !== user.id).map(m => m.id) : []); setChosenMessages([]); setGroupTitle(chat?.title || 'Reading group'); setSharing(mode); } catch(e) { report(e); }
  }
  async function confirmShare() {
    if (!chat) return; setBusy(true); setError(''); try {
      if (sharing === 'project') { const c = await api<{id:string}>('/research/projects/' + copyProject + '/discussions', { title: groupTitle, paper_ids: chat.scope.paper_ids, source_session_id: chat.id, message_ids: chosenMessages }); await openChat(c.id); await history(); }
      else if (sharing === 'members') { await api('/chat/sessions/' + chat.id + '/members', { member_ids: invitees }, 'PUT'); await openChat(chat.id); }
      else { const c = await api<Discussion>('/chat/sessions/' + chat.id + '/share', { title: groupTitle, member_ids: invitees, message_ids: chosenMessages }); await openChat(c.id); await history(); }
      setSharing(null); setNotice('Sharing updated. Only the listed members can open this discussion.');
    } catch(e) { report(e); } finally { setBusy(false); }
  }
  useEffect(() => { document.querySelector('.workspace')?.scrollTo(0, 0); }, [paper?.id, chat?.id, comparison?.id, showProjects, projectId]);
  const nameOf = (id: string | null) => groupMembers.find(m => m.id === id)?.name || (id === user.id ? 'You' : 'Member');
  return <main className="reading-layout"><aside className="library"><div className="library-top"><span className="eyebrow">YOUR LIBRARY</span><h1>Reading room</h1><button className="projects-nav" aria-pressed={showProjects} onClick={() => { setShowProjects(true); setProjectId(null); setPaper(null); setChat(null); setComparison(null); loadProjects().catch(report); }}>My research & projects →</button><div className="tabs"><button aria-pressed={!savedOnly} onClick={() => { setSavedOnly(false); setOffset(0); }}>All papers</button><button aria-pressed={savedOnly} onClick={() => { setSavedOnly(true); setOffset(0); }}>My saved</button></div>
      <form onSubmit={e => { e.preventDefault(); setOffset(0); setSearch(q); }}><label className="sr-only" htmlFor="paper-search">Search paper titles</label><input id="paper-search" value={q} onChange={e => setQ(e.target.value)} placeholder="Search paper titles"/><button>Search</button></form>
      {selected.length > 0 && <div className="selection">{selected.length} selected <button disabled={selected.length < 2} onClick={compare}>Compare →</button><label className="dimension-input">Dimensions<input aria-label="Comparison dimensions" value={dimensions} onChange={e => setDimensions(e.target.value)} maxLength={640}/></label><button onClick={() => setSelected([])}>Clear</button></div>}</div>
      <div className="paper-list">{papers.map(p => <article key={p.id} className={paper?.id === p.id ? 'active' : ''}><input type="checkbox" aria-label={'Select ' + p.title} checked={selected.includes(p.id)} onChange={e => setSelected(ids => e.target.checked ? [...ids, p.id].slice(0,6) : ids.filter(id => id !== p.id))}/><button className="paper-title" onClick={() => { openPaper(p.id, true).catch(report); }}><small>{p.year || 'Date unavailable'} · {p.venue || 'Publication'} {p.saved ? '· Saved' : ''}</small><strong>{p.title}</strong><span>{p.full_text_available ? 'Full-text evidence' : 'Metadata / abstract'}</span></button></article>)}{!papers.length && <p className="empty">{savedOnly ? 'Your saved papers will appear here.' : 'No matching papers.'}</p>}</div>
      <div className="actions pager"><button disabled={!offset} onClick={() => setOffset(n => Math.max(0,n-40))}>Previous</button><button disabled={!more} onClick={() => setOffset(n => n+40)}>Next</button></div>
      <div className="history"><h2>My comparisons</h2>{myComparisons.map(c => <button key={c.id} onClick={() => api<Comparison>('/research/comparisons/' + c.id).then(showComparison).catch(report)}>{c.title}</button>)}<h2>My discussions</h2>{chats.map(c => <button key={c.id} className={c.id === chat?.id ? 'active' : ''} onClick={() => openChat(c.id).catch(report)}><span>{c.shared ? 'GROUP' : 'PRIVATE'}</span>{c.title || 'Untitled discussion'}</button>)}</div>
    </aside><section className="workspace">
      {error && <div role="alert" className="error">{error}<button onClick={() => setError('')}>Dismiss</button></div>}{notice && <div role="status" className="notice">{notice}<button onClick={() => setNotice('')}>Dismiss</button></div>}
      {!showProjects && !paper && !chat && !comparison && <div className="empty-workspace"><span className="eyebrow">READ WITH CONTEXT</span><h2>Start with a paper.<br/>Follow the evidence.</h2><p>Open a title on the left, or select up to six papers to compare. Your bookmarks, notes and questions belong to you.</p></div>}
      {showProjects && <Projects user={user} projectId={projectId} projects={projects} onProjects={loadProjects} onSelect={selectProject} onPaper={id => openPaper(id, true).catch(report)} onChat={id => openChat(id).catch(report)} onComparison={showComparison} onSource={locate}/>}
      {paper && <article className="reader"><div className="eyebrow">{paper.venue || 'PUBLICATION'} · {paper.year || 'UNDATED'}</div><h1>{paper.title}</h1><p className="byline">{paper.authors.join(', ')}</p><div className="actions"><button className="primary" onClick={() => startChat([paper.id]).catch(report)}>Ask about this paper</button><button onClick={savePaper}>{paper.saved ? 'Save my note' : 'Save paper'}</button>{paper.saved && <button onClick={() => api('/reading/saved/' + encodeURIComponent(paper.id), undefined, 'DELETE').then(() => { setPaper({...paper,saved:false,note:''});setNote('');loadPapers().catch(report); }).catch(report)}>Remove saved</button>}{safeLink(paper.url) && <a href={safeLink(paper.url)} target="_blank" rel="noreferrer">Publisher ↗</a>}</div>
        <details className="private-note"><summary>My private note</summary><label htmlFor="note">Only you can see this note. It is not copied to group discussions.</label><textarea id="note" value={note} onChange={e => setNote(e.target.value)} maxLength={6000} placeholder="What matters for your work?"/><button onClick={savePaper}>Save privately</button></details>
        <div className="actions"><label>Add paper to project<select defaultValue="" onChange={async e => { const id = e.target.value; e.target.value = ''; if (!id) return; try { await api('/research/projects/' + id + '/papers/' + encodeURIComponent(paper.id), {}, 'PUT'); setNotice('Paper added. Private notes and chats were not copied.'); } catch(err) { report(err); } }}><option value="">Choose project…</option>{projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label></div>
        <h2>Abstract</h2>{paper.abstract && <button onClick={() => setSource({paper_id:paper.id,kind:'abstract',source_id:paper.id})}>Annotate abstract ↗</button>}<Text value={paper.abstract || 'No abstract is available in the catalogue.'}/>
        <div className="evidence-title"><h2>Source text</h2><span className="badge">{paper.markdown_status === 'original' ? 'Markdown available' : paper.markdown_status === 'indexed_sections' ? 'Indexed sections available' : 'Full text not yet available'}</span></div>
        {paper.markdown_status !== 'unavailable' && <div className="actions"><button onClick={() => api<{text:string}>('/reading/papers/'+encodeURIComponent(paper.id)+'/markdown').then(r=>setMarkdown(r.text)).catch(report)}>Read Markdown</button><a href={'/api/reading/papers/'+encodeURIComponent(paper.id)+'/markdown?download=true'}>Download .md</a></div>}
        {markdown ? <Text value={markdown}/> : paper.sections?.length ? paper.sections.map(s => <details id={'source-'+s.id} key={s.id}><summary>{s.heading}{s.page_start ? ' · p. '+s.page_start : ''}</summary><button onClick={() => setSource({paper_id:paper.id,kind:'section',source_id:s.id})}>Locate & annotate passage ↗</button><Text value={s.text}/></details>) : <p className="empty">Questions can use the available abstract and catalogue information. Full-text claims need the original paper.</p>}
      </article>}
      {comparison && <EvidenceComparison key={comparison.id} value={comparison} user={user} projects={projects} onChange={setComparison} onRevoked={() => { setComparison(null); setError('This project comparison is no longer available to you.'); }} onSource={locate} onAsk={async ids => { try { if (comparison.project_id) { const c = await api<{id:string}>('/research/projects/' + comparison.project_id + '/discussions', {title:comparison.title, paper_ids:ids}); await openChat(c.id); } else await startChat(ids); } catch(e) { report(e); } }}/>}
      {chat && <section className="discussion"><div className="discussion-head"><div><span className="eyebrow">{chat.shared ? 'SELECTED MEMBERS ONLY' : 'PRIVATE · ONLY YOU'}</span><h2>{chat.title || 'Paper discussion'}</h2><p>{chat.shared ? groupMembers.map(m=>m.name).join(' · ') : 'This conversation is not visible to other Slack or PAS users.'}</p></div><div className="actions">{!chat.project_id && chat.owner_id===user.id && <button onClick={()=>share('copy')}>Share selected messages</button>}{!chat.project_id && chat.shared && chat.owner_id===user.id && <button onClick={()=>share('members')}>Manage members</button>}{!chat.project_id && chat.owner_id===user.id && <button disabled={!projects.length} onClick={() => share('project')}>Copy selected to project</button>}{chat.project_id && <button onClick={() => selectProject(chat.project_id!)}>Open project</button>}{chat.shared && <button onClick={()=>navigator.clipboard.writeText(linkTo('discussion',chat.id)).then(()=>setNotice('Link copied. Forward it to your Slack group; only selected PAS members can open it.')).catch(report)}>Copy group link</button>}</div></div>
        <div className="scope">Papers in this discussion: {(chat.scope.paper_ids||[]).map(id=><button key={id} onClick={()=>openPaper(id).catch(report)}>{id===paper?.id ? paper.title : papers.find(p => p.id === id)?.title || 'Open selected paper'}</button>)}</div>
        {chat.messages?.map(m=><article key={m.id} className={'message '+m.role}><div className="message-label">{m.role==='assistant' ? 'PAS · '+sourceText(m) : nameOf(m.reader_id)}</div><Text value={m.content}/>{m.sources?.length>0 && <div className="sources">{m.sources.map((s,i)=><details key={i}><summary><button onClick={()=>s.anchor ? locate(s.anchor) : setSource({paper_id:s.paper_id,kind:s.chunk_id?'chunk':s.section_id?'section':'abstract',source_id:s.chunk_id||s.section_id||s.paper_id})}>[{i+1}] {s.paper_title || s.paper_id}</button>{s.section_type ? ' · '+s.section_type : ''}</summary><Text value={s.text || s.snippet || 'Open the paper to inspect the indexed source.'}/></details>)}</div>}</article>)}
        <p className="model-status">{modelStatus}</p><form className="composer" onSubmit={e=>{e.preventDefault();ask();}}><label htmlFor="question">{chat.shared ? 'Ask PAS or leave a comment for this group' : 'Ask a question about the selected papers'}</label><textarea id="question" value={question} onChange={e=>setQuestion(e.target.value)} maxLength={2000} placeholder="Which passage supports the main claim?"/><div className="actions"><button className="primary" disabled={busy || !question.trim()}>{busy ? 'Working with the evidence…' : 'Ask PAS'}</button>{chat.shared && <button type="button" disabled={busy || !question.trim()} onClick={()=>ask(true)}>Post a group comment</button>}<small>{chat.shared ? 'Visible to listed members.' : 'Private to you.'} Answers depend on available evidence.</small></div></form>
      </section>}
    </section>
    {sharing && chat && <div className="modal-backdrop"><section className="share-dialog" role="dialog" aria-modal="true" aria-labelledby="share-title">{error && <p className="error" role="alert">{error}</p>}<h2 id="share-title">{sharing==='project' ? 'Copy selected messages into a project' : sharing==='copy' ? 'Create a separate group discussion' : 'Manage discussion access'}</h2><p>{sharing!=='members' ? 'Your original conversation and private notes stay private. Only the selected messages below will be copied.' : 'Removing a member blocks future access. It cannot erase copies they have already read or saved.'}</p>{sharing!=='members' && <label>Group title<input value={groupTitle} onChange={e=>setGroupTitle(e.target.value)} maxLength={160}/></label>}{sharing==='project' ? <label>Destination project<select value={copyProject} onChange={e => setCopyProject(e.target.value)}><option value="">Choose project…</option>{projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select><small>All current and future project members can read the selected messages. Add the discussion's papers to the project first.</small></label> : <><h3>Who can open this discussion?</h3><p>You remain its owner.</p>{!members.length && <p>No colleagues have connected yet. Ask them to open PAS and sign in through AC Papers first.</p>}{members.map(m=><label className="choice" key={m.id}><input type="checkbox" checked={invitees.includes(m.id)} onChange={e=>setInvitees(ids=>e.target.checked?[...ids,m.id]:ids.filter(id=>id!==m.id))}/>{m.name}</label>)}</>}{sharing!=='members' && <><h3>Messages to copy ({chosenMessages.length})</h3><p>Leave all unchecked to start with the paper selection only.</p>{chat.messages.map(m=><label key={m.id} className="choice message-choice"><input type="checkbox" checked={chosenMessages.includes(m.id)} onChange={e=>setChosenMessages(ids=>e.target.checked?[...ids,m.id]:ids.filter(id=>id!==m.id))}/><span><strong>{m.role==='assistant'?'PAS':nameOf(m.reader_id)}</strong><Text value={m.content}/></span></label>)}</>}<div className="actions"><button onClick={()=>setSharing(null)}>Cancel</button><button className="primary" disabled={busy || (sharing!=='members' && (!(sharing==='project'?copyProject:invitees.length) || !groupTitle.trim()))} onClick={confirmShare}>{sharing==='project'?'Copy selected to project':sharing==='copy'?'Create this group copy':'Save member access'}</button></div></section></div>}
    {source && <EvidenceReader key={source.source_id} target={source} user={user} projects={projects} onClose={() => setSource(null)}/>}
  </main>;
}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
