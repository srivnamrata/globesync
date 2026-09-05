import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError } from '../services/apiClient';
import { server } from '../test/server';

describe('ApiClient', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('merges scoped and request headers with bearer authentication', async () => {
    server.use(http.post('http://api.test/projects', async ({ request }) => {
      expect(request.headers.get('authorization')).toBe('Bearer token-1');
      expect(request.headers.get('x-workspace-id')).toBe('workspace-1');
      expect(request.headers.get('x-request-id')).toBe('request-1');
      expect(request.headers.get('accept')).toBe('application/json');
      expect(request.headers.get('content-type')).toBe('application/json');
      expect(await request.json()).toEqual({ name: 'Demo' });
      return HttpResponse.json({ id: 'project-1' });
    }));
    const client = new ApiClient('http://api.test');
    client.setToken('token-1');
    client.setDefaultHeaders({
      'X-Workspace-Id': ' workspace-1 ',
      Empty: ' ',
      Missing: null,
    });

    await expect(client.post('/projects', { name: 'Demo' }, {
      headers: { 'X-Request-Id': 'request-1' },
    })).resolves.toEqual({ id: 'project-1' });
  });

  it('does not force JSON content type for form data and can clear auth', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const client = new ApiClient('http://api.test');
    client.setToken('temporary');
    client.clearToken();

    await expect(client.post('/upload', new FormData())).resolves.toEqual({ ok: true });
    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(headers.get('authorization')).toBeNull();
    expect(headers.get('content-type')).toBeNull();
  });

  it.each([
    [{ message: 'Message detail' }, 'Message detail'],
    [{ detail: 'API detail' }, 'API detail'],
    [{ error: { message: 'Nested detail' } }, 'Nested detail'],
    [{}, 'HTTP error! Status: 400'],
  ])('maps API error payloads', async (payload, expected) => {
    server.use(http.get('http://api.test/failure', () => HttpResponse.json(payload, { status: 400 })));
    const client = new ApiClient('http://api.test');

    await expect(client.get('/failure')).rejects.toMatchObject({
      name: 'ApiError',
      status: 400,
      message: expected,
      data: payload,
    });
  });

  it('retries temporary overloads and succeeds', async () => {
    let attempts = 0;
    server.use(http.get('http://api.test/retry', () => {
      attempts += 1;
      return attempts === 1
        ? HttpResponse.json({ message: 'Busy' }, { status: 503 })
        : HttpResponse.json({ ok: true });
    }));
    const client = new ApiClient('http://api.test');

    await expect(client.request('/retry', {}, 1, 0)).resolves.toEqual({ ok: true });
    expect(attempts).toBe(2);
  });

  it('retries explicit fetch failures and preserves exhausted errors', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new Error('Fetch failed'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    const client = new ApiClient('http://api.test');

    await expect(client.request('/network', {}, 1, 0)).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    fetchMock.mockRejectedValueOnce(new Error('Fetch failed permanently'));
    await expect(client.request('/network', {}, 0, 0))
      .rejects.toThrow('Fetch failed permanently');
  });

  it('provides typed convenience methods', async () => {
    const client = new ApiClient('http://api.test');
    const request = vi.spyOn(client, 'request').mockResolvedValue({ ok: true });

    await client.get('/one');
    await client.put('/two', { value: 2 });
    await client.patch('/three', { value: 3 });
    await client.delete('/four');

    expect(request.mock.calls).toEqual([
      ['/one', { method: 'GET' }],
      ['/two', { method: 'PUT', body: '{"value":2}' }],
      ['/three', { method: 'PATCH', body: '{"value":3}' }],
      ['/four', { method: 'DELETE' }],
    ]);
  });

  it('constructs ApiError values', () => {
    const error = new ApiError('No access', 403, { code: 'denied' });
    expect(error).toMatchObject({
      name: 'ApiError',
      message: 'No access',
      status: 403,
      data: { code: 'denied' },
    });
  });
});
