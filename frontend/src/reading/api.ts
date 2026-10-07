export type Reader = { id: string; name: string; workspace_id: string; role: 'member' | 'admin' };
export type Section = { id: string; heading: string; text: string; page_start: number | null; page_end: number | null };
export type Paper = { id: string; title: string; abstract: string | null; doi: string | null; year: number | null; venue: string | null;
  authors: string[]; full_text_available: boolean; saved: boolean; note: string; url: string | null; sections?: Section[]; markdown_status?: string };
export type Source = { paper_id: string; paper_title?: string; section_id?: string; chunk_id?: string; text?: string; snippet?: string; section_type?: string; anchor?: Anchor };
export type Message = { id: string; role: string; content: string; reader_id: string | null; answer_kind: string | null; sources: Source[]; audit: Record<string, unknown> };
export type Discussion = { id: string; title: string | null; owner_id: string; shared: boolean; project_id?: string | null; messages: Message[]; scope: { paper_ids?: string[] } };
export async function api<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch('/api' + path, { credentials: 'same-origin', cache: 'no-store',
    method: method || (body === undefined ? 'GET' : 'POST'),
    headers: { 'Content-Type': 'application/json', 'X-PAS-Request': '1' },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/me' && path !== '/auth/connect/complete') window.dispatchEvent(new Event('pas-auth-lost'));
    const result = await response.json().catch(() => ({}));
    throw new Error(typeof result.detail === 'string' ? result.detail : 'The request could not be completed.');
  }
  return response.json() as Promise<T>;
}
export function identityChanged() {
  sessionStorage.removeItem('pas.global-tier1-chat-session.v4');
  localStorage.setItem('pas.identity.changed', String(Date.now()));
}
export function safeLink(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try { const value = new URL(url); return ['https:', 'http:'].includes(value.protocol) ? value.href : undefined; } catch { return undefined; }
}
export type Anchor = { paper_id: string; paper_title: string; kind: 'section' | 'chunk' | 'abstract'; source_id: string; version: string; start: number; end: number; quote: string; heading: string; page_start?: number | null };
export type SourceDocument = Omit<Anchor, 'start' | 'end' | 'quote'> & { text: string };
export type Annotation = { id: string; owner_id: string; project_id: string | null; paper_id: string; anchor: Anchor; body: string; created_at: number };
export type Project = { id: string; title: string; question: string; owner_id: string; members: Reader[]; papers: Pick<Paper, 'id' | 'title' | 'year' | 'venue'>[]; discussions: { id: string; title: string }[] };
export type MatrixCell = { paper_id: string; dimension: string; interpretation: string; status: string; evidence: Anchor[] };
export type Comparison = { id: string; title: string; owner_id: string; project_id: string | null; paper_ids: string[]; dimensions: string[]; cells: MatrixCell[]; papers: Pick<Paper, 'id' | 'title'>[]; basis: string };
export function sourceUrl(paperId: string, kind: string, id: string) { return '/reading/papers/' + encodeURIComponent(paperId) + '/sources/' + encodeURIComponent(kind) + '/' + encodeURIComponent(id); }
