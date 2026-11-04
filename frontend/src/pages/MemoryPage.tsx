import { useCallback, useEffect, useState, useRef } from 'react';
import { Download, Search, Plus, Trash2, Pencil, Check, X, Database, LockKeyhole } from 'lucide-react';
import { api, displayDate, errorMessage } from '../services/api';
import type { Memory, MemoryCategory } from '../services/api';
const categories: MemoryCategory[] = ['personal', 'operational', 'conversation', 'system'];
export default function MemoryPage() {
  const [items, setItems] = useState<Memory[]>([]);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<MemoryCategory>('personal');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);
  const requestVersion = useRef(0);
  const queryRef = useRef(query); queryRef.current = query;
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; requestVersion.current++; }; }, []);
  const load = useCallback(async () => { const version = ++requestVersion.current; setLoading(true); try { const next = await api<Memory[]>(`/memories?q=${encodeURIComponent(queryRef.current)}`); if (mounted.current && version === requestVersion.current) { setItems(next); setError(''); } } catch (e) { if (mounted.current && version === requestVersion.current) setError(errorMessage(e)); } finally { if (mounted.current && version === requestVersion.current) setLoading(false); } }, []);
  useEffect(() => { requestVersion.current++; const timer = setTimeout(load, 200); return () => clearTimeout(timer); }, [load, query]);
  async function save() { if (!content.trim()) return; setBusy(true); try { await api('/memories', { method: 'POST', body: JSON.stringify({ category, content: content.trim() }) }); setContent(''); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  async function update(id: string) { setBusy(true); try { await api(`/memories/${id}`, { method: 'PATCH', body: JSON.stringify({ content: editContent.trim() }) }); setEditing(null); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  async function remove(id: string) { setBusy(true); try { await api(`/memories/${id}`, { method: 'DELETE' }); setDeleting(null); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  async function exportMemories() { try { const data = await api<unknown>('/memories/export'); const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = 'fred-memory-export.json'; link.click(); URL.revokeObjectURL(url); } catch (e) { setError(errorMessage(e)); } }
  return <div className="page-content">
    <div className="page-heading"><div><div className="eyebrow">PERSISTENT CONTEXT</div><h2>A memory you control.</h2><p>Review, correct, and remove what FRED knows.</p></div><button className="secondary-button" onClick={exportMemories}><Download size={15}/> Export</button></div>
    <div className="privacy-note"><LockKeyhole size={17}/><span>Only details you explicitly save enter memory. Avoid storing passwords, credentials, or sensitive records.</span></div>
    {error && <div role="alert" className="error-banner">{error}</div>}
    <section className="surface memory-create"><div className="section-title"><Plus size={16}/><h3>Save a memory</h3></div><textarea aria-label="New memory" disabled={busy} value={content} maxLength={4000} onChange={e => setContent(e.target.value)} placeholder="A preference, project detail, or decision worth remembering…" rows={3}/><div className="form-bottom"><select aria-label="Memory category" disabled={busy} value={category} onChange={e => setCategory(e.target.value as MemoryCategory)}>{categories.map(item => <option key={item} value={item}>{item.charAt(0).toUpperCase() + item.slice(1)}</option>)}</select><button className="primary-button" disabled={busy || !content.trim()} onClick={save}><Plus size={15}/>Save memory</button></div></section>
    <div className="memory-toolbar"><h3>Stored context <span>{items.length}</span></h3><label className="search-input"><Search size={15}/><input aria-label="Search memories" placeholder="Search memory" value={query} maxLength={200} onChange={e => { requestVersion.current++; setQuery(e.target.value); }}/></label></div>
    {loading ? <p className="muted">Retrieving memory…</p> : items.length === 0 ? <div className="empty-state"><Database size={28}/><h3>{query ? 'No matching memories' : 'A clean slate.'}</h3><p>{query ? 'Try another search term.' : 'Save a detail above. FRED can use relevant memories in future conversations.'}</p></div> : <div className="memory-list">{items.map(item => <article className="surface memory-card" key={item.id}><div className="memory-card-heading"><span className="category-label">{item.category}</span><span className="small-muted">Updated {displayDate(item.updated_at)}</span></div>{editing === item.id ? <><textarea aria-label="Edit memory" disabled={busy} value={editContent} onChange={e => setEditContent(e.target.value)} rows={3} maxLength={4000}/><div className="row-actions"><button className="secondary-button" onClick={() => setEditing(null)}><X size={14}/>Cancel</button><button className="primary-button" disabled={busy || !editContent.trim()} onClick={() => update(item.id)}><Check size={14}/>Save correction</button></div></> : <><p className="memory-content">{item.content}</p><div className="row-actions">{deleting === item.id ? <><span className="small-muted">Permanently delete this memory?</span><button className="text-button" onClick={() => setDeleting(null)}>Keep</button><button className="danger-button" disabled={busy} onClick={() => remove(item.id)}>Delete</button></> : <><button className="text-button" onClick={() => { setEditing(item.id); setEditContent(item.content); }}><Pencil size={13}/>Correct</button><button className="text-button" onClick={() => setDeleting(item.id)}><Trash2 size={13}/>Delete</button></>}</div></>}</article>)}</div>}
  </div>;
}
