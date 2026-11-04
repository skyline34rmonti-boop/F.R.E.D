import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MemoryPage from './MemoryPage';
import { api } from '../services/api';
import type { Memory } from '../services/api';

vi.mock('../services/api', async importOriginal => ({
  ...await importOriginal<typeof import('../services/api')>(),
  api: vi.fn(),
}));

const mockedApi = vi.mocked(api);
const memory: Memory = {
  id: 'memory-1',
  category: 'personal',
  content: 'Use concise executive updates.',
  created_at: '2026-11-02T12:00:00Z',
  updated_at: '2026-11-02T12:00:00Z',
};

beforeEach(() => mockedApi.mockReset());

describe('owner-managed memory', () => {
  it('retains the submitted detail and displays the error when saving fails', async () => {
    const user = userEvent.setup();
    mockedApi.mockResolvedValueOnce([]);
    render(<MemoryPage />);
    await screen.findByText('A clean slate.');
    await user.type(screen.getByLabelText('New memory'), 'Prefer a short morning briefing.');
    mockedApi.mockRejectedValueOnce(new Error('Memory could not be saved. Please retry.'));
    await user.click(screen.getByRole('button', { name: 'Save memory' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Memory could not be saved. Please retry.');
    expect(screen.getByLabelText('New memory')).toHaveValue('Prefer a short morning briefing.');
  });

  it('does not remove an existing memory when deletion fails', async () => {
    const user = userEvent.setup();
    mockedApi.mockResolvedValueOnce([memory]);
    render(<MemoryPage />);
    await screen.findByText(memory.content);
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(screen.getByText('Permanently delete this memory?')).toBeVisible();
    mockedApi.mockRejectedValueOnce(new Error('Deletion was not completed.'));
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Deletion was not completed.');
    expect(screen.getByText(memory.content)).toBeVisible();
  });

  it('shows the server-saved record after a successful creation', async () => {
    const user = userEvent.setup();
    mockedApi.mockResolvedValueOnce([]);
    render(<MemoryPage />);
    await screen.findByText('A clean slate.');
    await user.type(screen.getByLabelText('New memory'), memory.content);
    mockedApi.mockResolvedValueOnce(memory).mockResolvedValueOnce([memory]);
    await user.click(screen.getByRole('button', { name: 'Save memory' }));
    expect(await screen.findByText(memory.content)).toBeVisible();
    expect(screen.getByLabelText('New memory')).toHaveValue('');
  });

  it('keeps newer search results when an earlier request completes late', async () => {
    mockedApi.mockResolvedValueOnce([]);
    render(<MemoryPage />);
    await screen.findByText('A clean slate.');

    let resolveEarlier!: (value: Memory[]) => void;
    const earlier = new Promise<Memory[]>(resolve => { resolveEarlier = resolve; });
    mockedApi.mockImplementationOnce(() => earlier);
    fireEvent.change(screen.getByLabelText('Search memories'), { target: { value: 'earlier' } });
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith('/memories?q=earlier'));

    mockedApi.mockResolvedValueOnce([{ ...memory, content: 'Latest search result.' }]);
    fireEvent.change(screen.getByLabelText('Search memories'), { target: { value: 'latest' } });
    await screen.findByText('Latest search result.');
    await act(async () => { resolveEarlier([{ ...memory, content: 'Stale search result.' }]); });
    expect(screen.getByText('Latest search result.')).toBeVisible();
    expect(screen.queryByText('Stale search result.')).not.toBeInTheDocument();
  });
});
