import { useEffect, useState } from 'react';
import { api } from './api';
import type { Anchor, Annotation, Comparison, Project, Reader } from './api';
import { Exploration } from './Exploration';

export function Projects({ user, projectId, projects, onProjects, onSelect, onPaper, onChat, onComparison, onSource }: {
  user: Reader; projectId: string | null; projects: Project[]; onProjects: () => Promise<void>; onSelect: (id: string) => void;
  onPaper: (id: string) => void; onChat: (id: string) => void; onComparison: (c: Comparison) => void; onSource: (a: Anchor) => void;
}) {
  const [project, setProject] = useState<Project | null>(null), [title, setTitle] = useState(''), [question, setQuestion] = useState('');
  const [annotations, setAnnotations] = useState<Annotation[]>([]), [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [error, setError] = useState(''), [available, setAvailable] = useState<Reader[] | null>(null), [invitees, setInvitees] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]), [dimensions, setDimensions] = useState('Materials, Methods, Conditions, Baselines, Results, Limitations'), [busy, setBusy] = useState(false);
  async function load(id: string) {
    const [p, a, c] = await Promise.all([api<Project>('/research/projects/' + id), api<Annotation[]>('/research/annotations?project_id=' + id), api<Comparison[]>('/research/comparisons?project_id=' + id)]);
    return { p, a, c };
  }
  const apply = ({ p, a, c }: Awaited<ReturnType<typeof load>>) => { setProject(p); setAnnotations(a); setComparisons(c); };
  useEffect(() => {
    let active = true; setProject(null); setAnnotations([]); setComparisons([]); setSelected([]); setAvailable(null); setError('');
    if (!projectId) return;
    const refresh = () => load(projectId).then(r => { if (active) apply(r); }).catch(e => { if (active) { setProject(null); setAnnotations([]); setComparisons([]); setAvailable(null); setError(e.message); } });
    refresh(); const timer = window.setInterval(refresh, 12000); window.addEventListener('focus', refresh);
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, [projectId]);
  async function create() { setBusy(true); try { const p = await api<Project>('/research/projects', { title, question }); await onProjects(); setTitle(''); setQuestion(''); onSelect(p.id); } catch(e) { setError((e as Error).message); } finally { setBusy(false); } }
  async function compare() { if (!project) return; setBusy(true); try { const c = await api<Comparison>('/research/comparisons', { title: project.title + ' · comparison', project_id: project.id, paper_ids: selected, dimensions: dimensions.split(',').map(d => d.trim()).filter(Boolean) }); onComparison(c); } catch(e) { setError((e as Error).message); } finally { setBusy(false); } }
  return <section className="project-space"><span className="eyebrow">MY RESEARCH / PROJECTS</span>{error && <p className="error" role="alert">{error}</p>}
    {!projectId ? <><h1>Bring a research question.</h1><p>Gather papers, evidence comparisons and selected notes in one place. New projects start private.</p><div className="project-grid">{projects.map(p => <button key={p.id} className="project-card" onClick={() => onSelect(p.id)}><strong>{p.title}</strong><span>{p.question || 'A space for papers and evidence'}</span></button>)}</div>
      <form className="annotation-form" onSubmit={e => { e.preventDefault(); create(); }}><h2>Create a project</h2><label>Project name<input required value={title} onChange={e => setTitle(e.target.value)} maxLength={160}/></label><label>Research question<textarea value={question} onChange={e => setQuestion(e.target.value)} maxLength={3000}/></label><button className="primary" disabled={busy || !title.trim()}>Create private project</button></form></> : project && <>
      <h1>{project.title}</h1><p>{project.question}</p><p className="badge">{project.members.length === 1 ? 'Private project' : 'Selected members only'} · {project.members.map(m => m.name).join(' · ')}</p>
      <div className="actions"><button onClick={() => navigator.clipboard.writeText(location.origin + '/reading/?project=' + project.id).catch(() => setError('Copy the address from your browser.'))}>Copy project link</button>{project.owner_id === user.id && <button onClick={async () => { try { setAvailable(await api<Reader[]>('/chat/members')); setInvitees(project.members.filter(m => m.id !== user.id).map(m => m.id)); } catch(e) { setError((e as Error).message); } }}>Manage project members</button>}</div>
      {available && <div className="annotation-form"><h3>Who can see this project?</h3><p>Selected members can read all project papers, annotations, tables and discussions, including existing content. Personal notes outside this project stay private.</p>{available.map(m => <label className="choice" key={m.id}><input type="checkbox" checked={invitees.includes(m.id)} onChange={e => setInvitees(ids => e.target.checked ? [...ids, m.id] : ids.filter(id => id !== m.id))}/>{m.name}</label>)}<div className="actions"><button onClick={() => setAvailable(null)}>Cancel</button><button className="primary" onClick={async () => { try { await api('/research/projects/' + project.id + '/members', { member_ids: invitees }, 'PUT'); apply(await load(project.id)); setAvailable(null); } catch(e) { setError((e as Error).message); } }}>Save access</button></div></div>}
      <h2>Project papers</h2><p className="muted">Open a paper in the library and choose “Add to project”. Adding a paper does not copy personal notes or conversations.</p>
      {project.papers.map(p => <article className="project-paper" key={p.id}><input type="checkbox" aria-label={'Compare ' + p.title} checked={selected.includes(p.id)} onChange={e => setSelected(ids => e.target.checked ? [...ids, p.id].slice(0,6) : ids.filter(id => id !== p.id))}/><button onClick={() => onPaper(p.id)}>{p.title}</button>{project.owner_id === user.id && <button onClick={async () => { try { await api('/research/projects/' + project.id + '/papers/' + encodeURIComponent(p.id), undefined, 'DELETE'); apply(await load(project.id)); setSelected(ids => ids.filter(id => id !== p.id)); } catch(e) { setError((e as Error).message); } }}>Remove from folder</button>}</article>)}
      {!!project.papers.length && <div className="annotation-form"><label>Comparison dimensions (separate with commas)<input value={dimensions} onChange={e => setDimensions(e.target.value)} maxLength={640}/></label><div className="actions"><button disabled={busy || selected.length < 2} onClick={compare}>Compare selected ({selected.length})</button><button disabled={busy || !selected.length} onClick={async () => { try { const c = await api<{id:string}>('/research/projects/' + project.id + '/discussions', { title: project.title, paper_ids: selected }); onChat(c.id); } catch(e) { setError((e as Error).message); } }}>Discuss selected papers</button></div><small>Removing a paper from this folder retains evidence already saved in annotations, comparisons and discussions.</small></div>}
      <Exploration key={project.id+user.id} project={project} user={user} annotations={annotations} onPaper={onPaper} onSource={onSource} onRefresh={async()=>apply(await load(project.id))}/>
      <h2>Evidence comparisons</h2>{!comparisons.length && <p className="muted">Select two or more papers to create a table, or copy a private table here.</p>}{comparisons.map(c => <button key={c.id} onClick={() => api<Comparison>('/research/comparisons/' + c.id).then(onComparison).catch(e => setError(e.message))}>{c.title}</button>)}
      <h2>Shared passages & notes</h2>{!annotations.length && <p className="muted">No annotations have been shared here.</p>}{annotations.map(a => <article className="annotation" key={a.id}><blockquote>{a.anchor.quote}</blockquote><p>{a.body}</p><small>{project.members.find(m => m.id === a.owner_id)?.name || 'Former member'} · {a.anchor.paper_title}</small><button onClick={() => onSource(a.anchor)}>Locate original passage ↗</button></article>)}
      <h2>Project discussions</h2>{!project.discussions.length && <p className="muted">Start with selected papers or copy selected messages from your private discussion.</p>}{project.discussions.map(c => <button key={c.id} onClick={() => onChat(c.id)}>{c.title}</button>)}
    </>}
  </section>;
}
