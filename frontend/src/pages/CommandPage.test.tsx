import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CommandPage from './CommandPage';
import { api } from '../services/api';
import type { Settings } from '../services/api';
import type { ServerState } from '../hooks/useSocket';
vi.mock('../services/api', async importOriginal => ({ ...await importOriginal<typeof import('../services/api')>(), api: vi.fn() }));
const settings: Settings = { mode: 'standard', model: 'gpt-4.1-mini', provider: 'mock', owner_name: 'Owner' };
const idle: ServerState = { connected: true, status: 'idle', conversationId: null };
const mockedApi = vi.mocked(api);
beforeEach(() => { mockedApi.mockReset(); });
function Harness({ server = idle }: { server?: ServerState }) { const [prefs, setPrefs] = useState(settings); return <CommandPage settings={prefs} onSettings={setPrefs} server={server}/>; }
describe('command interface state', () => {
  it('greets the configured owner instead of a hardcoded identity', async () => {
    mockedApi.mockResolvedValue([]);
    render(<CommandPage settings={{ ...settings, owner_name: 'Example Owner' }} onSettings={vi.fn()} server={idle}/>);
    expect(screen.getByRole('heading', { name: 'At your service, Example Owner.' })).toBeInTheDocument();
    expect(screen.queryByText('At your service, Owner.')).not.toBeInTheDocument();
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith('/conversations'));
  });
  it('refreshes persisted communication mode after a text command', async () => {
    mockedApi.mockImplementation(async (path, options) => {
      if (path === '/conversations') return [];
      if (path === '/settings') return { ...settings, mode: 'executive' };
      if (path === '/chat') { expect(JSON.parse(String(options?.body))).not.toHaveProperty('mode'); return { conversation_id: 'c1', message: { id: 'a', role: 'assistant', content: 'Executive mode enabled, Owner.', created_at: new Date().toISOString() }, provider: 'mock' }; }
      if (path.includes('/messages')) return [{ id: 'a', role: 'assistant', content: 'Executive mode enabled, Owner.', created_at: new Date().toISOString() }];
      throw new Error(`Unexpected path ${path}`);
    });
    render(<Harness/>);
    await userEvent.type(screen.getByLabelText('Message FRED'), 'Fred, executive mode.');
    await userEvent.click(screen.getByLabelText('Send message'));
    await screen.findByText('Executive mode enabled, Owner.');
    expect(screen.getByLabelText('Communication mode')).toHaveValue('executive');
    expect(screen.getByRole('img', { name: 'FRED intelligence core: ready' })).toBeInTheDocument();
  });
  it('uses actual server state to keep the core and composer busy across navigation', async () => {
    mockedApi.mockResolvedValue([]);
    const view = render(<Harness server={{ connected: true, status: 'thinking', conversationId: 'c1' }}/>);
    expect(screen.getByLabelText('Message FRED')).toBeDisabled();
    expect(screen.getByRole('img', { name: 'FRED intelligence core: thinking' })).toBeInTheDocument();
    expect(screen.getByLabelText('Request in progress')).toBeDisabled();
    view.rerender(<Harness server={idle}/>);
    await waitFor(() => expect(screen.getByLabelText('Message FRED')).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Message FRED'), { target: { value: 'Ready now' } });
    expect(screen.getByLabelText('Send message')).toBeEnabled();
  });
});
