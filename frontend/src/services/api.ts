export type User = { username: string; display_name: string };
export type Session = { user: User; csrf_token: string };
export type Mode = 'standard' | 'executive' | 'casual' | 'focus' | 'briefing';
export type Settings = { mode: Mode; model: string; provider: string; owner_name: string };
export type Conversation = { id: string; title: string; created_at: string };
export type Message = { id: string; role: 'user' | 'assistant'; content: string; created_at: string };
export type MemoryCategory = 'personal' | 'operational' | 'conversation' | 'system';
export type Memory = { id: string; category: MemoryCategory; content: string; created_at: string; updated_at: string };
export type Integration = { id: string; name: string; status: string; detail: string };
export type System = { provider: string; model: string; database: string; integrations: Integration[] };
let csrf = '';
export function setCsrf(value: string) { csrf = value; }
export class ApiError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status; } }
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD'].includes(method) && csrf) headers.set('X-CSRF-Token', csrf);
  let response: Response;
  try { response = await fetch(`/api${path}`, { ...options, headers, credentials: 'include' }); }
  catch (error) { if (error instanceof DOMException && error.name === 'AbortError') throw error; throw new ApiError('FRED’s service is unavailable. Check that the backend is running on port 8000.', 0); }
  if (!response.ok) { const payload = await response.json().catch(() => ({})); const detail = typeof payload.detail === 'string' ? payload.detail : response.status === 422 ? 'Please check the submitted values.' : 'The request could not be completed.'; throw new ApiError(detail, response.status); }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export const modes: { value: Mode; label: string; detail: string }[] = [
  { value: 'standard', label: 'Standard', detail: 'Thoughtful, conversational, efficient.' },
  { value: 'executive', label: 'Executive', detail: 'Concise analysis and clear decisions.' },
  { value: 'casual', label: 'Casual', detail: 'Relaxed conversation, a little wit.' },
  { value: 'focus', label: 'Focus', detail: 'Short responses. Minimal interruptions.' },
  { value: 'briefing', label: 'Briefing', detail: 'Structured, factual summaries.' },
];
export function errorMessage(error: unknown) { return error instanceof Error ? error.message : 'Something went wrong. Please try again.'; }
export function displayDate(value: string) { return new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }); }
