import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Activity, ArrowRight, BriefcaseBusiness, ChevronRight, Command, Cpu, Database, House, Layers3, LoaderCircle, LockKeyhole, LogOut, Menu, Settings2, ShieldCheck, X } from 'lucide-react';
import IntelligenceCore from './components/IntelligenceCore';
import RightRail from './components/RightRail';
import CommandPage from './pages/CommandPage';
import MemoryPage from './pages/MemoryPage';
import SettingsPage from './pages/SettingsPage';
import { IntegrationsPage, ProjectsPage, PropertiesPage } from './pages/WorkspacePages';
import { useSocket } from './hooks/useSocket';
import { api, ApiError, errorMessage, setCsrf } from './services/api';
import type { Session, Settings, System } from './services/api';
type Page = 'command' | 'projects' | 'properties' | 'integrations' | 'memory' | 'settings';
const navigation: { id: Page; label: string; icon: typeof Command; section?: string }[] = [
  { id: 'command', label: 'Command center', icon: Command, section: 'WORKSPACES' },
  { id: 'projects', label: 'Projects (demo)', icon: BriefcaseBusiness },
  { id: 'properties', label: 'Properties', icon: House },
  { id: 'integrations', label: 'Integrations', icon: Layers3, section: 'SYSTEM' },
  { id: 'memory', label: 'Memory', icon: Database },
  { id: 'settings', label: 'Settings', icon: Settings2 },
];
function Login({ onSession }: { onSession: (session: Session) => void }) {
  const [username, setUsername] = useState('owner');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function login(e: React.FormEvent) { e.preventDefault(); setBusy(true); setError(''); try { const session = await api<Session>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }); setPassword(''); onSession(session); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  return <div className="login-page"><div className="login-grid"/><header className="login-header"><a href="/" aria-label="FRED home" className="brand"><span className="brand-symbol">F</span><span>F R E D<small>PERSONAL INTELLIGENCE</small></span></a><span className="login-version">FOUNDATION RELEASE / 0.1</span></header><main className="login-main"><div className="login-identity"><IntelligenceCore state={busy ? 'thinking' : 'idle'}/><div className="eyebrow">INTELLIGENCE. PRECISELY.</div><h1>A considered presence.<br/>At your command.</h1><p>Your private intelligence and operations platform.<br/>Built to remember, reason, and grow with you.</p></div><form className="login-card" onSubmit={login}><div className="login-lock"><LockKeyhole size={20}/></div><span className="eyebrow">AUTHORIZED ACCESS</span><h2>Welcome back.</h2><p>Authenticate to enter your workspace.</p>{error && <div role="alert" className="error-banner">{error}</div>}<label className="field-label" htmlFor="username">Username</label><input id="username" className="field-input" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required disabled={busy}/><label className="field-label" htmlFor="password">Password</label><input id="password" className="field-input" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required disabled={busy}/><button className="login-submit primary-button" disabled={busy}>{busy ? 'Authenticating…' : 'Enter command center'}{busy ? <LoaderCircle className="spin" size={17}/> : <ArrowRight size={17}/>}</button><div className="login-help"><ShieldCheck size={14}/><span>Use the owner credentials configured in your server’s <code>.env</code> file.</span></div></form></main><footer className="login-footer"><span>F.R.E.D. / PERSONAL AI INTELLIGENCE &amp; AUTOMATION</span><span>PRIVATE BY DESIGN</span></footer></div>;
}
export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [booting, setBooting] = useState(true);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [system, setSystem] = useState<System | null>(null);
  const [page, setPage] = useState<Page>('command');
  const [error, setError] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const reduced = useReducedMotion();
  const live = useSocket(!!session);
  function acceptSession(next: Session) { setCsrf(next.csrf_token); setSession(next); setError(''); }
  useEffect(() => { let active = true; api<Session>('/auth/me').then(s => { if (active) acceptSession(s); }).catch(e => { if (active && !(e instanceof ApiError && e.status === 401)) setError(errorMessage(e)); }).finally(() => { if (active) setBooting(false); }); return () => { active = false; }; }, []);
  useEffect(() => {
    if (!session) return;
    let active = true;
    async function load() { try { const [nextSettings, nextSystem] = await Promise.all([api<Settings>('/settings'), api<System>('/system')]); if (active) { setSettings(nextSettings); setSystem(nextSystem); setError(''); } } catch (e) { if (active) { if (e instanceof ApiError && e.status === 401) { setSession(null); setCsrf(''); setSettings(null); setSystem(null); } else { setError(errorMessage(e)); setSystem(null); } } } }
    void load(); const timer = setInterval(load, 30000); return () => { active = false; clearInterval(timer); };
  }, [session]);
  async function logout() { setLoggingOut(true); try { await api('/auth/logout', { method: 'POST' }); setSession(null); setCsrf(''); setSettings(null); setSystem(null); setPage('command'); setError(''); } catch (e) { setError(errorMessage(e)); } finally { setLoggingOut(false); } }
  function navigate(next: Page) { setPage(next); setSidebarOpen(false); }
  if (booting) return <div className="boot-screen"><span className="brand-symbol">F</span><p><LoaderCircle className="spin" size={15}/> Establishing secure session</p></div>;
  if (!session) return <><Login onSession={acceptSession}/>{error && <div className="connection-toast" role="status">{error}</div>}</>;
  const activeNav = navigation.find(item => item.id === page)!;
  const ownerName = session.user.display_name || session.user.username;
  const ownerInitials = ownerName.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'O';
  return <div className="app-shell">{sidebarOpen && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}/>}<aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}><div className="sidebar-brand"><a className="brand" href="/" onClick={e => { e.preventDefault(); navigate('command'); }}><span className="brand-symbol">F</span><span>F R E D<small>PERSONAL INTELLIGENCE</small></span></a><button className="icon-button sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"><X size={17}/></button></div><div className="owner-workspace"><span className="workspace-avatar">{ownerInitials}</span><div><strong>{ownerName}’s workspace</strong><small>PERSONAL / PRIVATE</small></div><LockKeyhole size={12}/></div><nav aria-label="Main navigation">{navigation.map(item => <div key={item.id}>{item.section && <div className="nav-section-label">{item.section}</div>}<button className={`nav-item ${page === item.id ? 'selected' : ''}`} onClick={() => navigate(item.id)} aria-current={page === item.id ? 'page' : undefined}><item.icon size={17}/><span>{item.label}</span>{page === item.id && <ChevronRight size={13}/>}</button></div>)}</nav><div className="sidebar-bottom"><div className="foundation-card"><span className="foundation-icon"><Cpu size={17}/></span><div><strong>{system ? 'Foundation online' : 'Service unavailable'}</strong><p>VERSION 0.1</p></div><span className="small-status-dot"/></div><div className="owner-profile"><div className="profile-avatar">{ownerInitials}</div><div><strong>{ownerName}</strong><small>Owner access</small></div><button className="icon-button" title="Sign out" aria-label="Sign out" disabled={loggingOut} onClick={logout}><LogOut size={15}/></button></div></div></aside><div className="main-shell"><header className="topbar"><div className="topbar-title"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Menu size={19}/></button><span className="topbar-prefix">FRED</span><ChevronRight size={12}/><h1>{activeNav.label}</h1></div><div className="topbar-status"><span className="version-label">V 0.1</span><span className="topbar-separator"/><span className={system ? 'connection-status' : 'connection-status disconnected'}><i/>{system ? 'SYSTEM ONLINE' : 'CONNECTING'}</span><span className="topbar-session"><ShieldCheck size={14}/><span>Secure session</span></span></div></header><div className="workspace-body"><main className="main-content" id="main-content">{error && <div role="alert" className="error-banner global-error">{error}</div>}{!settings ? <div className="workspace-loading"><LoaderCircle className="spin" size={22}/><p>Loading your workspace…</p></div> : <AnimatePresence mode="wait"><motion.div key={page} className="page-motion" initial={reduced ? false : { opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={reduced ? {} : { opacity: 0 }} transition={{ duration: 0.16 }}>{page === 'command' && <CommandPage settings={settings} onSettings={setSettings} server={live}/>} {page === 'memory' && <MemoryPage/>}{page === 'settings' && <SettingsPage settings={settings} onSave={setSettings}/>} {page === 'projects' && <ProjectsPage/>}{page === 'properties' && <PropertiesPage/>}{page === 'integrations' && <IntegrationsPage system={system}/>}</motion.div></AnimatePresence>}</main><RightRail system={system} live={live.connected} onIntegrations={() => navigate('integrations')}/></div><footer className="system-footer"><span><Activity size={11}/> FRED CORE / {settings?.provider === 'openai' ? 'OPENAI' : 'LOCAL MOCK'}<span className="footer-divider">·</span> PHASE 1 FOUNDATION</span><span>INTELLIGENCE. RELIABILITY. PRECISION.</span></footer></div></div>;
}
