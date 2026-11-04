import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, setCsrf } from './api';

describe('authenticated API transport', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    setCsrf('');
  });

  afterEach(() => {
    setCsrf('');
    vi.unstubAllGlobals();
  });

  it('sends the authenticated cookie and CSRF token on a write', async () => {
    setCsrf('session-specific-token');
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 'memory-1' })));

    await expect(api('/memories', { method: 'POST', body: JSON.stringify({ content: 'Approved preference' }) }))
      .resolves.toEqual({ id: 'memory-1' });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/memories');
    expect(options?.credentials).toBe('include');
    const headers = new Headers(options?.headers);
    expect(headers.get('X-CSRF-Token')).toBe('session-specific-token');
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('does not attach CSRF tokens to read requests', async () => {
    setCsrf('session-specific-token');
    fetchMock.mockResolvedValue(new Response('[]'));
    await api('/memories');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('preserves a readable provider error and its HTTP status', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'OpenAI authentication failed. Check the server-side key.' }), { status: 502 }));
    await expect(api('/chat', { method: 'POST' })).rejects.toMatchObject({
      status: 502,
      message: 'OpenAI authentication failed. Check the server-side key.',
    });
  });

  it('handles successful deletion without trying to decode an empty body', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api('/memories/memory-1', { method: 'DELETE' })).resolves.toBeUndefined();
  });

  it('turns a failed network request into an actionable service error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(api('/settings')).rejects.toMatchObject({ status: 0, message: expect.stringContaining('backend is running on port 8000') });
  });

  it('preserves cancellation instead of reporting a service outage', async () => {
    const cancellation = new DOMException('Cancelled', 'AbortError');
    fetchMock.mockRejectedValue(cancellation);
    await expect(api('/chat')).rejects.toBe(cancellation);
  });

  it('handles non-JSON server errors without exposing arbitrary response content', async () => {
    fetchMock.mockResolvedValue(new Response('<html>upstream failure</html>', { status: 503 }));
    await expect(api('/system')).rejects.toBeInstanceOf(ApiError);
    fetchMock.mockResolvedValue(new Response('<html>upstream failure</html>', { status: 503 }));
    await expect(api('/system')).rejects.toMatchObject({ status: 503, message: 'The request could not be completed.' });
  });
});
