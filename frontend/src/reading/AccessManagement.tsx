import { useEffect, useState } from 'react';
import { api } from './api';
import type { Reader } from './api';
type Member = Reader & { active: boolean };
type Audit = { id: string; actor_id: string; target_id: string; action: string; created_at: number; changes: unknown };
export function AccessManagement({ user }: { user: Reader }) {
  const [members, setMembers] = useState<Member[]>([]), [audit, setAudit] = useState<Audit[]>([]);
  const [query, setQuery] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState('');
  async function refresh() { const [people, events] = await Promise.all([api<Member[]>('/access/members?q=' + encodeURIComponent(query)), api<Audit[]>('/access/audit')]); setMembers(people); setAudit(events); }
  useEffect(() => { refresh().catch(e => setError(e.message)); }, []);
  async function update(person: Member, admin: boolean, active: boolean) {
    setBusy(person.id); setError('');
    try { await api('/access/members/' + encodeURIComponent(person.id), { admin, active }, 'PUT'); if (person.id === user.id) location.assign('/reading/'); else await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(''); }
  }
  const name = (id: string) => members.find(m => m.id === id)?.name || id;
  return <main className="workspace"><a href="/reading/">← Reading room</a><h1>Workspace access</h1>
    <p>Members can read papers and keep their own notes. Administrators can also use attribution analytics, institution comparisons and exports.</p>
    <p>Admin access does not grant access to someone else’s private conversations or notes. At least one administrator must remain active.</p>
    {error && <p role="alert" className="error">{error}</p>}
    <form className="actions" onSubmit={e => { e.preventDefault(); refresh().catch(e => setError(e.message)); }}><label>Find a registered member <input value={query} maxLength={100} onChange={e => setQuery(e.target.value)} /></label><button>Search</button></form>
    <table className="access-table"><thead><tr><th>Member</th><th>Access</th><th>Account</th><th>Change access</th></tr></thead><tbody>{members.map(m => <tr key={m.id}><td>{m.name}{m.id === user.id && ' (you)'}</td><td>{m.role}</td><td>{m.active ? 'Active' : 'Disabled'}</td><td className="actions"><button disabled={!!busy} onClick={() => update(m, m.role !== 'admin', m.active)}>{m.role === 'admin' ? 'Remove admin' : 'Grant admin'}</button><button disabled={!!busy} onClick={() => update(m, m.role === 'admin', !m.active)}>{m.active ? 'Disable account' : 'Enable account'}</button></td></tr>)}</tbody></table>
    <h2>Recent access changes</h2><p>Only access changes appear here. Private research content is excluded.</p>
    <ol>{audit.map(a => <li key={a.id}><time>{new Date(a.created_at * 1000).toLocaleString()}</time> · {name(a.actor_id)} → {name(a.target_id)} · {a.action}<pre>{JSON.stringify(a.changes, null, 2)}</pre></li>)}</ol>
  </main>;
}
