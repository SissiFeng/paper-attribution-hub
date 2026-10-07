import { useEffect, useRef, useState } from 'react';
import { api, sourceUrl } from './api';
import type { Anchor, Annotation, Project, Reader, SourceDocument } from './api';

export function EvidenceReader({ target, user, projects, onClose }: {
  target: { paper_id: string; kind: string; source_id: string; anchor?: Anchor }; user: Reader; projects: Project[]; onClose: () => void;
}) {
  const [source, setSource] = useState<SourceDocument | null>(null), [selection, setSelection] = useState<Anchor | null>(null);
  const [notes, setNotes] = useState<Annotation[]>([]), [body, setBody] = useState(''), [project, setProject] = useState('');
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null), [editBody, setEditBody] = useState('');
  const textRef = useRef<HTMLPreElement>(null), marker = useRef<HTMLElement>(null), closeRef = useRef<HTMLButtonElement>(null);
  const refresh = () => api<Annotation[]>('/research/annotations?' + new URLSearchParams({ paper_id: target.paper_id, ...(project ? { project_id: project } : {}) })).then(setNotes);
  useEffect(() => { let active = true; setSource(null); setSelection(null); setError('');
    api<SourceDocument>(sourceUrl(target.paper_id, target.kind, target.source_id)).then(s => { if (active) setSource(s); }).catch(e => { if (active) setError(e.message); });
    closeRef.current?.focus();
    return () => { active = false; };
  }, [target]);
  useEffect(() => { let active = true; setNotes([]);
    const refreshNotes = () => api<Annotation[]>('/research/annotations?' + new URLSearchParams({ paper_id: target.paper_id, ...(project ? { project_id: project } : {}) })).then(n => { if (active) setNotes(n); }).catch(e => { if (active) { setNotes([]); setSelection(null); setBody(''); setError(e.message); } });
    refreshNotes(); const timer = window.setInterval(refreshNotes, 12000);
    return () => { active = false; window.clearInterval(timer); };
  }, [target.paper_id, project]);
  useEffect(() => { marker.current?.scrollIntoView({ block: 'center' }); }, [source]);
  function capture() {
    const picked = window.getSelection(), root = textRef.current;
    if (!source || !picked || !root || !picked.rangeCount || picked.isCollapsed) return;
    const range = picked.getRangeAt(0);
    if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return;
    const before = range.cloneRange(); before.selectNodeContents(root); before.setEnd(range.startContainer, range.startOffset);
    const start = Array.from(before.toString()).length, quote = range.toString(), end = start + Array.from(quote).length;
    if (!quote.trim() || end - start > 4000) { setError('Select a passage of up to 4,000 characters.'); return; }
    setSelection({ ...source, start, end, quote }); setNotice('Passage selected. Add a note, then save.');
  }
  async function save() {
    if (!selection) return; setBusy(true); setError('');
    try { await api('/research/annotations', { paper_id: target.paper_id, project_id: project || null, anchor: selection, body }); await refresh(); setBody(''); setSelection(null); setNotice(project ? 'Annotation saved to this project.' : 'Annotation saved privately.'); }
    catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function copy(note: Annotation, projectId: string) {
    if (!projectId) return;
    try { await api('/research/annotations/' + note.id + '/copy', { project_id: projectId }); setNotice('A separate copy is now visible to that project.'); }
    catch(e) { setError((e as Error).message); }
  }
  const anchor = target.anchor, current = !anchor || source?.version === anchor.version;
  const points = Array.from(source?.text || '');
  return <div className="modal-backdrop" onKeyDown={e => { if (e.key === 'Escape') onClose(); if (e.key === 'Tab') { const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input,textarea,select,[tabindex="0"]')); const first = items[0], last = items[items.length-1]; if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); } } }}><section className="source-dialog" role="dialog" aria-modal="true" aria-labelledby="source-title">
    <div className="actions"><span className="eyebrow">ORIGINAL PASSAGE</span><button ref={closeRef} onClick={onClose}>Close source</button></div>
    <h2 id="source-title">{source?.paper_title || 'Loading source…'}</h2>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
    {!current && <p className="error">The source changed since this citation was saved. The saved quote is retained below; reselect from the current text before making a new annotation.</p>}
    {anchor && !current && <blockquote>{anchor.quote}</blockquote>}
    {source && <><p className="badge">{source.heading}{source.page_start ? ' · p. ' + source.page_start : ''}{source.kind === 'abstract' ? ' · Abstract only' : ''}</p><p className="muted">Select text with your mouse or keyboard, then choose “Use selected passage”.</p>
      <pre className="source-text" ref={textRef} tabIndex={0} onMouseUp={capture}>{anchor && current ? <>{points.slice(0, anchor.start).join('')}<mark ref={marker}>{points.slice(anchor.start, anchor.end).join('')}</mark>{points.slice(anchor.end).join('')}</> : source.text}</pre><button onClick={capture}>Use selected passage</button>
      <div className="annotation-form"><label>Save to<select value={project} onChange={e => { setProject(e.target.value); setSelection(null); setBody(''); }}><option value="">Private · only me</option>{projects.map(p => <option key={p.id} value={p.id}>Project: {p.title}</option>)}</select></label><small>Project annotations are visible to its current and future members. Add the paper to the project first.</small>
        {selection && <blockquote>{selection.quote}</blockquote>}<label>Note on this passage<textarea value={body} onChange={e => setBody(e.target.value)} maxLength={6000}/></label><button className="primary" disabled={busy || !selection} onClick={save}>Save {project ? 'to project' : 'privately'}</button></div>
      <h3>{project ? 'Project annotations' : 'My private annotations'}</h3>{notes.length === 0 && <p className="muted">No annotations in this space yet.</p>}{notes.map(n => <article className="annotation" key={n.id}><blockquote>{n.anchor.quote}</blockquote>{editing === n.id ? <label>Edit annotation<textarea value={editBody} onChange={e => setEditBody(e.target.value)} maxLength={6000}/><button onClick={() => api('/research/annotations/' + n.id, {body:editBody}, 'PUT').then(() => {setEditing(null); return refresh();}).catch(e => setError(e.message))}>Save annotation changes</button><button onClick={() => setEditing(null)}>Cancel edit</button></label> : <p>{n.body || 'Saved quotation'}</p>}<small>{n.anchor.heading} · {n.owner_id === user.id ? 'You' : 'Project member'}</small>{n.owner_id === user.id && <div className="actions"><button onClick={() => {setEditing(n.id);setEditBody(n.body);}}>Edit annotation</button><button onClick={() => api('/research/annotations/' + n.id, undefined, 'DELETE').then(refresh).catch(e => setError(e.message))}>Delete annotation</button>{!n.project_id && <label>Copy this annotation to<select defaultValue="" onChange={e => { copy(n, e.target.value); e.target.value = ''; }}><option value="">Choose project…</option>{projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>}</div>}</article>)}
    </>}
  </section></div>;
}
