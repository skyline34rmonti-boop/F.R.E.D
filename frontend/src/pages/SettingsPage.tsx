import { useState } from 'react';
import { Check, ShieldCheck, AudioLines, Cpu, ArrowUpRight } from 'lucide-react';
import { api, errorMessage, modes } from '../services/api';
import type { Mode, Settings } from '../services/api';
export default function SettingsPage({ settings, onSave }: { settings: Settings; onSave: (settings: Settings) => void }) {
  const [mode, setMode] = useState<Mode>(settings.mode);
  const [model, setModel] = useState(settings.model);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  async function save() { setBusy(true); setNotice(''); setError(''); try { const next = await api<Settings>('/settings', { method: 'PUT', body: JSON.stringify({ mode, model }) }); onSave(next); setNotice('Preferences saved.'); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  return <div className="page-content"><div className="page-heading"><div><div className="eyebrow">SYSTEM PREFERENCES</div><h2>Precisely your FRED.</h2><p>Communication, intelligence, and privacy controls.</p></div></div>
    {error && <div role="alert" className="error-banner">{error}</div>}{notice && <div role="status" className="success-banner"><Check size={16}/>{notice}</div>}
    <section className="surface settings-section"><div className="section-title"><Cpu size={17}/><h3>Communication mode</h3></div><p className="muted">Adjust the delivery. Accuracy and authorization stay consistent.</p><div className="mode-options">{modes.map(item => <label className={`mode-option ${mode === item.value ? 'selected' : ''}`} key={item.value}><input type="radio" name="mode" value={item.value} checked={mode === item.value} onChange={() => setMode(item.value)}/><span><strong>{item.label}</strong><small>{item.detail}</small></span>{mode === item.value && <Check size={16}/>}</label>)}</div></section>
    <section className="surface settings-section"><div className="section-title"><Cpu size={17}/><h3>Intelligence provider</h3><span className="status-chip">{settings.provider === 'mock' ? 'MOCK PROVIDER' : 'OPENAI'}</span></div><p className="muted">The provider and API credentials are configured on the server.</p><label className="field-label" htmlFor="model">OpenAI model</label><input id="model" className="field-input" value={model} onChange={e => setModel(e.target.value)} maxLength={120}/><p className="field-hint">Applies when the server uses OpenAI. Model access depends on your API account.</p></section>
    <div className="settings-actions"><button className="primary-button" disabled={busy || !model.trim()} onClick={save}>{busy ? 'Saving…' : 'Save preferences'}<Check size={15}/></button></div>
    <section className="surface settings-section"><div className="section-title"><AudioLines size={17}/><h3>Voice interface</h3><span className="phase-tag">PHASE 2</span></div><p className="muted">Push-to-talk, transcription, and spoken replies are planned next. Microphone access is not requested in this release.</p><div className="subtle-divider"/><div className="section-title"><ShieldCheck size={17}/><h3>Privacy by design</h3></div><p className="muted">Session credentials stay in an HTTP-only cookie. Memories are explicitly saved, searchable, and removable. Conversation content is sent to OpenAI only when that provider is enabled.</p><a className="text-link" href="https://platform.openai.com/docs/models" target="_blank" rel="noreferrer">Supported OpenAI models <ArrowUpRight size={14}/></a></section>
  </div>;
}
