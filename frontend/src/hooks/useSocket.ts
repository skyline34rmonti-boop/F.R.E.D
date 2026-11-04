import { useEffect, useState } from 'react';
export type ServerState = { connected: boolean; status: 'idle' | 'thinking' | 'error' | 'unknown'; conversationId: string | null };
export function useSocket(enabled: boolean): ServerState {
  const [state, setState] = useState<ServerState>({ connected: false, status: 'unknown', conversationId: null });
  useEffect(() => {
    if (!enabled) { setState({ connected: false, status: 'unknown', conversationId: null }); return; }
    let disposed = false;
    let socket: WebSocket | undefined;
    let timer: ReturnType<typeof setTimeout>;
    function connect() {
      if (disposed) return;
      socket = new WebSocket(`${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/ws`);
      socket.onopen = () => setState(previous => ({ ...previous, connected: true }));
      socket.onmessage = event => {
        try {
          const data: unknown = JSON.parse(event.data);
          if (typeof data !== 'object' || data === null) return;
          const update = data as Record<string, unknown>;
          if (update.type !== 'status' || !['idle', 'thinking', 'error'].includes(String(update.status))) return;
          setState({ connected: true, status: update.status as ServerState['status'], conversationId: typeof update.conversation_id === 'string' ? update.conversation_id : null });
        } catch { /* Ignore malformed, non-authoritative status events. */ }
      };
      socket.onclose = () => { if (disposed) return; setState(previous => ({ ...previous, connected: false, status: 'unknown' })); timer = setTimeout(connect, 5000); };
      socket.onerror = () => socket?.close();
    }
    connect();
    return () => { disposed = true; clearTimeout(timer); socket?.close(); };
  }, [enabled]);
  return state;
}
