import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authContextFixture } from '../test/fixtures';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  setDefaultHeaders: vi.fn(),
}));

vi.mock('../services/apiClient', () => ({ apiClient: api }));

import { AuthService } from '../services/authService';

const envKeys = [
  'NEXT_PUBLIC_AUTH_TOKEN',
  'NEXT_PUBLIC_GOOGLE_CLIENT_ID',
  'NEXT_PUBLIC_DEBUG_USER_EMAIL',
  'NEXT_PUBLIC_DEBUG_USER_SUBJECT',
  'NEXT_PUBLIC_DEBUG_USER_NAME',
  'NEXT_PUBLIC_DEBUG_WORKSPACE_ID',
] as const;

function clearAuthEnvironment() {
  envKeys.forEach((key) => vi.stubEnv(key, ''));
}

function jwt(exp: number): string {
  return `header.${btoa(JSON.stringify({ exp })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_')}.signature`;
}

describe('AuthService', () => {
  beforeEach(() => {
    clearAuthEnvironment();
    vi.clearAllMocks();
    delete window.google;
  });

  it('returns null without bootstrap inputs and explains required configuration', async () => {
    const service = new AuthService();

    expect(service.hasBootstrapConfig()).toBe(false);
    await expect(service.bootstrap()).resolves.toBeNull();
    await expect(service.ensureAuthenticatedContext())
      .rejects.toThrow('Frontend auth bootstrap is not configured');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('bootstraps once, caches the context, and notifies subscribers', async () => {
    vi.stubEnv('NEXT_PUBLIC_AUTH_TOKEN', 'environment-token');
    api.post.mockResolvedValue(authContextFixture);
    const service = new AuthService();
    const listener = vi.fn();
    const unsubscribe = service.subscribeToAuthState(listener);

    const first = service.bootstrap();
    const second = service.bootstrap();

    await expect(Promise.all([first, second])).resolves.toEqual([
      authContextFixture,
      authContextFixture,
    ]);
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith('/auth/bootstrap', {});
    expect(api.setToken).toHaveBeenCalledWith('environment-token');
    expect(listener).toHaveBeenCalledWith(authContextFixture);
    expect(JSON.parse(localStorage.getItem('globesync.auth_context')!))
      .toEqual(authContextFixture);

    unsubscribe();
    service.signOut();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('uses a valid stored token and removes an expired token', async () => {
    const service = new AuthService();
    localStorage.setItem('globesync.auth_token', jwt(Math.floor(Date.now() / 1000) + 3600));
    api.post.mockResolvedValue(authContextFixture);

    await service.bootstrap();
    expect(api.setToken).toHaveBeenCalledWith(expect.stringContaining('header.'));

    localStorage.clear();
    api.setToken.mockClear();
    api.clearToken.mockClear();
    localStorage.setItem('globesync.auth_token', jwt(Math.floor(Date.now() / 1000) - 3600));
    const expiredService = new AuthService();
    await expect(expiredService.bootstrap()).resolves.toBeNull();
    expect(localStorage.getItem('globesync.auth_token')).toBeNull();
    expect(api.clearToken).not.toHaveBeenCalled();
  });

  it('trims tokens and configures workspace and debug headers', () => {
    vi.stubEnv('NEXT_PUBLIC_DEBUG_USER_EMAIL', ' editor@example.com ');
    vi.stubEnv('NEXT_PUBLIC_DEBUG_USER_SUBJECT', ' subject ');
    vi.stubEnv('NEXT_PUBLIC_DEBUG_USER_NAME', ' Editor ');
    vi.stubEnv('NEXT_PUBLIC_DEBUG_WORKSPACE_ID', 'debug-workspace');
    localStorage.setItem('globesync.active_workspace_id', ' active-workspace ');
    const service = new AuthService();

    service.setBearerToken(' browser-token ');

    expect(localStorage.getItem('globesync.auth_token')).toBe('browser-token');
    expect(api.setToken).toHaveBeenCalledWith('browser-token');
    expect(api.setDefaultHeaders).toHaveBeenLastCalledWith({
      'X-Debug-User-Email': 'editor@example.com',
      'X-Debug-User-Subject': 'subject',
      'X-Debug-User-Name': 'Editor',
      'X-Workspace-Id': 'active-workspace',
    });

    service.setBearerToken(null);
    expect(localStorage.getItem('globesync.auth_token')).toBeNull();
    expect(api.clearToken).toHaveBeenCalled();
  });

  it('discards malformed cached context and reads valid cached context', () => {
    const service = new AuthService();
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    localStorage.setItem('globesync.auth_context', '{bad json');

    expect(service.getCachedContext()).toBeNull();
    expect(localStorage.getItem('globesync.auth_context')).toBeNull();
    expect(warning).toHaveBeenCalled();

    localStorage.setItem('globesync.auth_context', JSON.stringify(authContextFixture));
    expect(service.getCachedContext()).toEqual(authContextFixture);
    expect(service.hasBootstrapConfig()).toBe(true);
  });

  it('keeps a cached context when server bootstrap credentials remain configured', async () => {
    vi.stubEnv('NEXT_PUBLIC_DEBUG_USER_EMAIL', 'editor@example.com');
    localStorage.setItem('globesync.auth_context', JSON.stringify(authContextFixture));
    const service = new AuthService();

    await expect(service.bootstrap()).resolves.toEqual(authContextFixture);
    expect(api.post).not.toHaveBeenCalled();
    expect(api.setDefaultHeaders).toHaveBeenCalled();
  });

  it('clears failed bootstrap state and permits a later retry', async () => {
    vi.stubEnv('NEXT_PUBLIC_AUTH_TOKEN', 'token');
    const failure = new Error('bootstrap failed');
    api.post.mockRejectedValueOnce(failure).mockResolvedValueOnce(authContextFixture);
    const service = new AuthService();
    const listener = vi.fn();
    service.subscribeToAuthState(listener);

    await expect(service.bootstrap()).rejects.toThrow('bootstrap failed');
    expect(listener).toHaveBeenCalledWith(null);
    expect(localStorage.getItem('globesync.auth_context')).toBeNull();
    await expect(service.bootstrap()).resolves.toEqual(authContextFixture);
  });

  it('lists workspace context and members through authenticated headers', async () => {
    vi.stubEnv('NEXT_PUBLIC_AUTH_TOKEN', 'token');
    api.get
      .mockResolvedValueOnce({ items: [authContextFixture] })
      .mockResolvedValueOnce({ items: [{ user_id: 'user-1', email: 'editor@example.com' }] });
    const service = new AuthService();

    await expect(service.listAvailableWorkspaces()).resolves.toEqual([authContextFixture]);
    await expect(service.listWorkspaceMembers()).resolves.toEqual([
      { user_id: 'user-1', email: 'editor@example.com' },
    ]);
    expect(api.get.mock.calls).toEqual([
      ['/auth/workspaces'],
      ['/auth/workspace-members'],
    ]);
  });

  it('switches workspace using the active workspace header', async () => {
    vi.stubEnv('NEXT_PUBLIC_AUTH_TOKEN', 'token');
    localStorage.setItem('globesync.auth_context', JSON.stringify(authContextFixture));
    api.post.mockResolvedValue(authContextFixture);
    const service = new AuthService();

    await expect(service.switchWorkspace('workspace-2')).resolves.toEqual(authContextFixture);
    expect(localStorage.getItem('globesync.active_workspace_id')).toBe('workspace-2');
    expect(api.setDefaultHeaders).toHaveBeenCalledWith(
      expect.objectContaining({ 'X-Workspace-Id': 'workspace-2' }),
    );
  });

  it('signs out and publishes the unauthenticated state', () => {
    const service = new AuthService();
    const listener = vi.fn();
    const disableAutoSelect = vi.fn();
    service.subscribeToAuthState(listener);
    window.google = { accounts: { id: {
      initialize: vi.fn(),
      renderButton: vi.fn(),
      prompt: vi.fn(),
      disableAutoSelect,
    } } };
    localStorage.setItem('globesync.auth_token', 'token');
    localStorage.setItem('globesync.auth_context', '{}');
    localStorage.setItem('globesync.active_workspace_id', 'workspace-1');

    service.signOut();

    expect(api.clearToken).toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(listener).toHaveBeenCalledWith(null);
    expect(disableAutoSelect).toHaveBeenCalled();
  });

  it('reports Google availability and renders an accessible provider button', async () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', 'google-client');
    const initialize = vi.fn();
    const renderButton = vi.fn();
    window.google = { accounts: { id: {
      initialize,
      renderButton,
      prompt: vi.fn(),
      disableAutoSelect: vi.fn(),
    } } };
    const service = new AuthService();
    const container = document.createElement('div');
    container.textContent = 'stale';

    await expect(service.isGoogleSignInAvailable()).resolves.toBe(true);
    await service.renderGoogleSignInButton(container);

    expect(container.innerHTML).toBe('');
    expect(initialize).toHaveBeenCalledWith(expect.objectContaining({
      client_id: 'google-client',
      auto_select: false,
    }));
    expect(renderButton).toHaveBeenCalledWith(container, expect.objectContaining({
      text: 'signin_with',
      width: 260,
    }));
  });

  it('rejects Google sign-in when it is unavailable', async () => {
    await expect(new AuthService().signInWithGoogle())
      .rejects.toThrow('Google sign-in is not configured');
    await expect(new AuthService().isGoogleSignInAvailable()).resolves.toBe(false);
  });

  it('exchanges a Google identity credential for workspace context', async () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', 'google-client');
    api.post.mockResolvedValue(authContextFixture);
    let latestCallback!: (response: { credential?: string }) => void;
    const initialize = vi.fn((options: {
      callback: (response: { credential?: string }) => void;
    }) => {
      latestCallback = options.callback;
    });
    const prompt = vi.fn(() => latestCallback({ credential: 'google-credential' }));
    window.google = { accounts: { id: {
      initialize,
      renderButton: vi.fn(),
      prompt,
      disableAutoSelect: vi.fn(),
    } } };
    const service = new AuthService();

    await expect(service.signInWithGoogle()).resolves.toEqual(authContextFixture);
    expect(localStorage.getItem('globesync.auth_token')).toBe('google-credential');
    expect(initialize).toHaveBeenCalledTimes(2);
    expect(prompt).toHaveBeenCalled();
  });

  it('rejects an empty Google identity response', async () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', 'google-client');
    let latestCallback!: (response: { credential?: string }) => void;
    window.google = { accounts: { id: {
      initialize: vi.fn((options) => {
        latestCallback = options.callback;
      }),
      renderButton: vi.fn(),
      prompt: vi.fn(() => latestCallback({})),
      disableAutoSelect: vi.fn(),
    } } };

    await expect(new AuthService().signInWithGoogle())
      .rejects.toThrow('did not return an identity token');
  });

  it('loads the Google identity script once and detects availability', async () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', 'google-client');
    const append = vi.spyOn(document.head, 'appendChild').mockImplementation((node) => {
      window.google = { accounts: { id: {
        initialize: vi.fn(),
        renderButton: vi.fn(),
        prompt: vi.fn(),
        disableAutoSelect: vi.fn(),
      } } };
      queueMicrotask(() => (node as HTMLScriptElement).onload?.(new Event('load')));
      return node;
    });
    const service = new AuthService();

    await expect(Promise.all([
      service.isGoogleSignInAvailable(),
      service.isGoogleSignInAvailable(),
    ])).resolves.toEqual([true, true]);
    expect(append).toHaveBeenCalledTimes(1);
  });

  it('surfaces Google identity script failures', async () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', 'google-client');
    vi.spyOn(document.head, 'appendChild').mockImplementation((node) => {
      queueMicrotask(() => (node as HTMLScriptElement).onerror?.(new Event('error')));
      return node;
    });

    await expect(new AuthService().isGoogleSignInAvailable())
      .rejects.toThrow('Failed to load Google Identity Services');
  });
});
