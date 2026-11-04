import { useEffect, useRef, useState } from 'react';
import { ArrowUp, ArrowUpRight, AudioLines, ChevronDown, ChevronRight, Clock3, Plus, LoaderCircle, Trash2, X, Sparkles, ShieldCheck } from 'lucide-react';
import IntelligenceCore from '../components/IntelligenceCore';
import { api, displayDate, errorMessage, modes } from '../services/api';
import type { ServerState } from '../hooks/useSocket';
import type { Conversation, Message, Mode, Settings } from '../services/api';
const starters = [ { label: 'Prepare a briefing', prompt: 'Fred, prepare my morning briefing using only the information available to you.' }, { label: 'What can you do?', prompt: 'Fred, what can you actually do in this version?' }, { label: 'Help me think it through', prompt: 'Fred, help me organize my priorities. Ask me what I’m working on.' } ];
export default function CommandPage({ settings, onSettings, server }: { settings: Settings; onSettings: (settings: Settings) => void; server: ServerState }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);
  const busy = pending || server.status === 'thinking';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const selection = useRef(0);
  const bottom = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { alive.current = true; void loadConversations(); return () => { alive.current = false; controller.current?.abort(); }; }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages, pending]);
  async function loadConversations() { try { const data = await api<Conversation[]>('/conversations'); if (alive.current) setConversations(data); } catch (e) { if (alive.current) setError(errorMessage(e)); } }
  async function selectConversation(id: string) { if (busy) return; const ticket = ++selection.current; setShowHistory(false); setLoading(true); setError(''); setNotice(''); try { const data = await api<Message[]>(`/conversations/${id}/messages`); if (alive.current && ticket === selection.current) { setConversationId(id); setMessages(data); } } catch (e) { if (alive.current && ticket === selection.current) setError(errorMessage(e)); } finally { if (alive.current && ticket === selection.current) setLoading(false); } }
  function newConversation() { if (busy) return; selection.current++; setConversationId(null); setMessages([]); setLoading(false); setError(''); setNotice(''); setShowHistory(false); textarea.current?.focus(); }
  async function deleteConversation(id: string) { if (busy) return; try { await api(`/conversations/${id}`, { method: 'DELETE' }); if (conversationId === id) newConversation(); setDeleteId(null); await loadConversations(); } catch (e) { setError(errorMessage(e)); } }
  async function changeMode(mode: Mode) { try { const next = await api<Settings>('/settings', { method: 'PUT', body: JSON.stringify({ mode }) }); onSettings(next); setNotice(`${modes.find(m => m.value === mode)?.label} mode enabled.`); } catch (e) { setError(errorMessage(e)); } }
  async function send(value = input) {
    const text = value.trim(); if (!text || busy || loading) return;
    setInput(''); setPending(true); setError(''); setNotice('');
    const optimistic: Message = { id: `local-${Date.now()}`, role: 'user', content: text, created_at: new Date().toISOString() };
    setMessages(prev => [...prev, optimistic]);
    const request = new AbortController(); controller.current = request;
    try {
      const result = await api<{ conversation_id: string; message: Message; provider: string }>('/chat', { method: 'POST', body: JSON.stringify({ message: text, conversation_id: conversationId ?? undefined}), signal: request.signal });
      if (!alive.current) return;
      setConversationId(result.conversation_id);
      const [history, preferences] = await Promise.all([api<Message[]>(`/conversations/${result.conversation_id}/messages`), api<Settings>('/settings')]);
      if (alive.current) { setMessages(history); onSettings(preferences); }
    } catch (e) {
      if (!alive.current) return;
      if (e instanceof DOMException && e.name === 'AbortError') return;
      setError(errorMessage(e));
      if (conversationId) { try { const history = await api<Message[]>(`/conversations/${conversationId}/messages`); if (alive.current) setMessages(history); } catch { /* Keep the submitted message visible when the service is unavailable. */ } }
    } finally { if (alive.current) { setPending(false); controller.current = null; await loadConversations(); textarea.current?.focus(); } }
  }
  const coreState = busy ? 'thinking' : error ? 'error' : 'idle';
  return <div className="command-page"><div className="command-toolbar"><div className="workspace-label"><span className="small-status-dot"/> PERSONAL WORKSPACE</div><div className="toolbar-actions"><button className={`icon-button ${showHistory ? 'active' : ''}`} title="Conversation history" aria-label="Conversation history" disabled={busy} onClick={() => setShowHistory(v => !v)}><Clock3 size={17}/></button><button className="toolbar-new" disabled={busy} onClick={newConversation}><Plus size={15}/><span>New conversation</span></button></div></div>
    {showHistory && <section className="history-panel surface"><div className="section-title"><Clock3 size={15}/><h3>Conversation history</h3><button className="icon-button" aria-label="Close history" onClick={() => setShowHistory(false)}><X size={15}/></button></div>{conversations.length === 0 ? <p className="muted">No saved conversations yet.</p> : conversations.map(c => <div className={`history-row ${c.id === conversationId ? 'selected' : ''}`} key={c.id}><button className="history-select" onClick={() => selectConversation(c.id)}><span>{c.title}</span><small>{displayDate(c.created_at)}</small></button>{deleteId === c.id ? <div className="history-delete"><button className="text-button" onClick={() => setDeleteId(null)}>Keep</button><button className="danger-button" disabled={busy} onClick={() => deleteConversation(c.id)}>Delete</button></div> : <button className="icon-button" aria-label={`Delete conversation ${c.title}`} disabled={busy} onClick={() => setDeleteId(c.id)}><Trash2 size={14}/></button>}</div>)}</section>}
    <div className={`intelligence-stage ${messages.length ? 'stage-conversation' : ''}`}><div className="stage-grid"/><div className="core-stage"><IntelligenceCore state={coreState} compact={messages.length > 0}/></div><div className="stage-description"><div className={`core-status ${coreState}`}><span/>{busy ? 'PROCESSING YOUR REQUEST' : error ? 'ATTENTION REQUIRED' : 'READY WHEN YOU ARE'}</div>{messages.length === 0 && <><h2>At your service, {settings.owner_name || 'Owner'}.</h2><p>A clear mind. A considered response.<br/>What shall we work on?</p></>}</div><div className="stage-annotation annotation-left"><span>PERSONAL INTELLIGENCE</span><strong>F.R.E.D.</strong></div><div className="stage-annotation annotation-right"><span>PROTOCOL</span><strong>{settings.mode.toUpperCase()}</strong></div></div>
    {settings.provider === 'mock' && <div className="mock-banner"><span className="mock-mark"/><span>LOCAL DEVELOPMENT <span className="mock-separator">/</span> Mock AI provider · Responses are demonstrations</span></div>}
    <div className="conversation-area" role="log" aria-label="Conversation transcript" aria-live="polite">{loading ? <p className="conversation-loading">Loading saved conversation…</p> : messages.length ? <div className="transcript">{messages.map(message => <article className={`message message-${message.role}`} key={message.id}><div className="message-avatar">{message.role === 'assistant' ? 'F' : (settings.owner_name.trim()[0]?.toUpperCase() || 'O')}</div><div className="message-body"><div className="message-author">{message.role === 'assistant' ? 'FRED' : 'YOU'}<span>{new Date(message.created_at.endsWith('Z') || /[+-]\d\d:\d\d$/.test(message.created_at) ? message.created_at : `${message.created_at}Z`).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</span></div><p>{message.content}</p></div></article>)}{busy && <div className="thinking-line"><Sparkles size={14}/><span>FRED is considering your request</span><span className="thinking-dots">•••</span></div>}<div ref={bottom}/></div> : <div className="suggestion-grid">{starters.map((starter, i) => <button className="suggestion" key={starter.label} onClick={() => send(starter.prompt)} disabled={busy || loading}><span className="suggestion-number">0{i + 1}</span><span>{starter.label}</span><ArrowUpRight size={15}/></button>)}</div>}</div>
    <div className="composer-area">{error && <div role="alert" className="error-banner">{error}<button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={14}/></button></div>}{notice && <div role="status" className="notice-banner">{notice}<button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={14}/></button></div>}<form className={`composer ${busy ? 'composer-busy' : ''}`} onSubmit={e => { e.preventDefault(); void send(); }}><label className="sr-only" htmlFor="command-input">Message FRED</label><textarea id="command-input" ref={textarea} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }} placeholder="Ask FRED, or give a command…" rows={1} maxLength={8000} disabled={busy || loading}/><div className="composer-bottom"><div className="composer-options"><div className="mode-select"><select aria-label="Communication mode" value={settings.mode} disabled={busy} onChange={e => changeMode(e.target.value as Mode)}>{modes.map(mode => <option key={mode.value} value={mode.value}>{mode.label} mode</option>)}</select><ChevronDown size={12}/></div><span className="composer-divider"/><button type="button" className="voice-disabled" disabled title="Push-to-talk and spoken replies arrive in Phase 2"><AudioLines size={16}/><span>Voice · Phase 2</span></button></div>{busy ? <button type="button" className="send-button" aria-label="Request in progress" disabled><LoaderCircle className="spin" size={16}/></button> : <button type="submit" className="send-button" aria-label="Send message" disabled={!input.trim() || loading || busy}><ArrowUp size={20}/></button>}</div></form><div className="composer-footnote"><span><ShieldCheck size={11}/>Actions require verified authorization.</span><span>Enter to send <ChevronRight size={10}/> Shift + Enter for a new line</span></div></div>
  </div>;
}
