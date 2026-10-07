import { useEffect, useState } from 'react';
import { api } from './api';
import type { Anchor, Annotation, Comparison, MatrixCell, Project, Reader } from './api';

export function EvidenceComparison({ value, user, projects, onChange, onSource, onAsk, onRevoked }: {
  value: Comparison; user: Reader; projects: Project[]; onChange: (v: Comparison) => void; onSource: (a: Anchor) => void; onAsk: (ids: string[]) => void; onRevoked: () => void;
}) {
  const [editing, setEditing] = useState<MatrixCell | null>(null), [text, setText] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [annotations, setAnnotations] = useState<Annotation[]>([]), [evidence, setEvidence] = useState<Anchor[]>([]);
  async function edit(cell: MatrixCell) {
    setEditing(cell); setText(cell.interpretation); setEvidence(cell.evidence); setAnnotations([]);
    try { setAnnotations(await api<Annotation[]>('/research/annotations?' + new URLSearchParams({paper_id:cell.paper_id,...(value.project_id ? {project_id:value.project_id} : {})}))); } catch(e) { setError((e as Error).message); }
  }
  useEffect(() => {
    if (!value.project_id) return;
    let active = true;
    const refresh = () => api<Comparison>('/research/comparisons/' + value.id).then(c => { if (active) onChange(c); }).catch(() => { if (active) onRevoked(); });
    const timer = window.setInterval(refresh, 12000); window.addEventListener('focus', refresh);
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, [value.id, value.project_id]);
  async function save() {
    if (!editing) return;
    try { onChange(await api<Comparison>('/research/comparisons/' + value.id + '/cells', { ...editing, interpretation: text, evidence }, 'PUT')); setEditing(null); }
    catch(e) { setError((e as Error).message); }
  }
  return <section className="evidence-comparison"><span className="eyebrow">{value.project_id ? 'PROJECT EVIDENCE' : 'PRIVATE EVIDENCE'}</span><h1>{value.title}</h1><p>{value.basis}</p>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status" className="notice">{notice}</p>}
    <div className="actions"><button className="primary" onClick={() => onAsk(value.paper_ids)}>Ask across these papers</button>{!value.project_id && value.owner_id === user.id && <label>Copy this table to<select defaultValue="" onChange={async e => { const id = e.target.value; e.target.value = ''; if (!id) return; try { await api('/research/comparisons/' + value.id + '/copy', { project_id: id }); setNotice('A separate copy is now visible in the project.'); } catch(err) { setError((err as Error).message); } }}><option value="">Choose project…</option>{projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>}</div>
    <div className="matrix-scroll"><table className="evidence-matrix"><thead><tr><th>Compare by</th>{value.papers.map(p => <th key={p.id}>{p.title}</th>)}</tr></thead><tbody>{value.dimensions.map(d => <tr key={d}><th>{d}</th>{value.papers.map(p => { const c = value.cells.find(c => c.paper_id === p.id && c.dimension === d)!; return <td key={p.id}>
      {c.interpretation && <div className="interpretation"><small>READER INTERPRETATION · VERIFY AGAINST THE SOURCE</small><p>{c.interpretation}</p></div>}
      {!c.evidence.length && <p className="muted">No matching evidence found. This is not evidence of absence.</p>}
      {c.evidence.map((a, i) => <div className="matrix-quote" key={i}><small>{a.kind === 'abstract' ? 'ABSTRACT ONLY' : 'SOURCE EXCERPT'}</small><blockquote>{a.quote}</blockquote><button onClick={() => onSource(a)}>Locate passage · {a.heading}{a.page_start ? ' · p. ' + a.page_start : ''} ↗</button></div>)}
      {value.owner_id === user.id && <button onClick={() => edit(c)}>Add interpretation</button>}
    </td>; })}</tr>)}</tbody></table></div>
    {editing && <div className="annotation-form"><h3>{editing.dimension} · your interpretation</h3><p>This note stays attached to the exact excerpts shown in the cell. Include units and conditions; do not infer missing values.</p>{evidence.map((a,i) => <blockquote key={i}>{a.quote}<button onClick={() => setEvidence(items => items.filter((_,n) => i!==n))}>Remove excerpt</button></blockquote>)}<label>Add a saved passage<select value="" disabled={evidence.length>=3} onChange={e => {const a=annotations.find(a => a.id===e.target.value);if(a)setEvidence(items => [...items,a.anchor]);}}><option value="">Choose an annotation…</option>{annotations.map(a => <option key={a.id} value={a.id}>{a.anchor.quote.slice(0,120)}</option>)}</select></label><p className="muted">To add a missing passage, open the paper and annotate it first. For a project table, explicitly copy the annotation into that project.</p><textarea aria-label="Cell interpretation" value={text} onChange={e => setText(e.target.value)} maxLength={2000}/><div className="actions"><button onClick={() => setEditing(null)}>Cancel</button><button className="primary" disabled={!evidence.length} onClick={save}>Save interpretation</button></div></div>}
  </section>;
}
