import { apiClient } from './apiClient';

export type WorkspaceRole = 'owner' | 'editor' | 'viewer';

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (options: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: Record<string, string | number | boolean>,
          ) => void;
          prompt: () => void;
          disableAutoSelect: () => void;
        };
      };
    };
  }
}

export interface AuthBootstrapResponse {
  user: {
    id: string;
    email: string;
    display_name: string | null;
    auth_provider: string;
    auth_subject: string | null;
    is_active: boolean;
    last_login_at: string | null;
    created_at: string;
    updated_at: string;
  };
  workspace: {
    id: string;
    name: string;
    slug: string | null;
    owner_user_id: string;
    is_personal: boolean;
    archived_at: string | null;
    created_at: string;
    updated_at: string;
  };
  membership: {
    workspace_id: string;
    user_id: string;
    role: WorkspaceRole;
    invited_by_user_id: string | null;
    joined_at: string | null;
    created_at: string;
    updated_at: string;
  };
  bootstrap_completed: boolean;
}

export type WorkspaceContext = Pick<AuthBootstrapResponse, 'workspace' | 'membership'>;

export type WorkspaceMember = {
  user_id: string;
  display_name: string | null;
  email: string;
  role: WorkspaceRole;
};

const AUTH_CONTEXT_STORAGE_KEY = 'globesync.auth_context';
const AUTH_TOKEN_STORAGE_KEY = 'globesync.auth_token';
const GOOGLE_IDENTITY_SCRIPT_ID = 'google-identity-services-client';
const AUTH_TOKEN_EXPIRY_SKEW_MS = 60 * 1000;
const ACTIVE_WORKSPACE_STORAGE_KEY = 'globesync.active_workspace_id';

function readWindowStorage(key: string): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const value = window.localStorage.getItem(key);
  return value && value.trim().length > 0 ? value.trim() : null;
}

function getStoredWorkspaceId(): string | null {
  return readWindowStorage(ACTIVE_WORKSPACE_STORAGE_KEY);
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const [, payloadSegment] = token.split('.');
  if (!payloadSegment) {
    return null;
  }

  try {
    const normalized = payloadSegment.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    const decoded = typeof window === 'undefined'
      ? Buffer.from(padded, 'base64').toString('utf-8')
      : window.atob(padded);
    return JSON.parse(decoded) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function isJwtExpired(token: string): boolean {
  const payload = decodeJwtPayload(token);
  const exp = payload?.exp;
  if (typeof exp !== 'number') {
    return false;
  }

  return (exp * 1000) <= (Date.now() + AUTH_TOKEN_EXPIRY_SKEW_MS);
}

function getConfiguredBearerToken(): string | null {
  const envToken = process.env.NEXT_PUBLIC_AUTH_TOKEN?.trim();
  if (envToken) {
    return envToken;
  }

  const storedToken = readWindowStorage(AUTH_TOKEN_STORAGE_KEY);
  if (!storedToken) {
    return null;
  }

  if (isJwtExpired(storedToken)) {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    }
    return null;
  }

  return storedToken;
}

function getGoogleClientId(): string | null {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID?.trim();
  return clientId && clientId.length > 0 ? clientId : null;
}

function getConfiguredDebugHeaders(): Record<string, string> {
  const debugHeaders: Record<string, string> = {};

  const email = process.env.NEXT_PUBLIC_DEBUG_USER_EMAIL?.trim();
  const subject = process.env.NEXT_PUBLIC_DEBUG_USER_SUBJECT?.trim();
  const name = process.env.NEXT_PUBLIC_DEBUG_USER_NAME?.trim();
  const workspaceId = process.env.NEXT_PUBLIC_DEBUG_WORKSPACE_ID?.trim();

  if (email) {
    debugHeaders['X-Debug-User-Email'] = email;
  }
  if (subject) {
    debugHeaders['X-Debug-User-Subject'] = subject;
  }
  if (name) {
    debugHeaders['X-Debug-User-Name'] = name;
  }
  if (workspaceId) {
    debugHeaders['X-Workspace-Id'] = workspaceId;
  }

  return debugHeaders;
}

function hasServerBootstrapInputs(): boolean {
  return Boolean(
    getConfiguredBearerToken()
    || getConfiguredDebugHeaders()['X-Debug-User-Email'],
  );
}

function hasBootstrapInputs(): boolean {
  return Boolean(hasServerBootstrapInputs() || getGoogleClientId());
}

export class AuthService {
  private bootstrapPromise: Promise<AuthBootstrapResponse | null> | null = null;
  private bootstrappedContext: AuthBootstrapResponse | null = null;
  private googleScriptPromise: Promise<void> | null = null;
  private googleIdentityInitialized = false;
  private authStateListeners = new Set<(context: AuthBootstrapResponse | null) => void>();

  hasBootstrapConfig(): boolean {
    return Boolean(this.getCachedContext() || hasBootstrapInputs());
  }

  subscribeToAuthState(listener: (context: AuthBootstrapResponse | null) => void): () => void {
    this.authStateListeners.add(listener);
    return () => {
      this.authStateListeners.delete(listener);
    };
  }

  setBearerToken(token: string | null) {
    if (typeof window !== 'undefined') {
      if (token && token.trim().length > 0) {
        window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token.trim());
      } else {
        window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      }
    }

    this.configureApiClient();
  }

  async listAvailableWorkspaces(): Promise<WorkspaceContext[]> {
    this.configureApiClient();
    const response = await apiClient.get<{ items: WorkspaceContext[] }>('/auth/workspaces');
    return response.items;
  }

  async listWorkspaceMembers(): Promise<WorkspaceMember[]> {
    this.configureApiClient();
    const response = await apiClient.get<{ items: WorkspaceMember[] }>('/auth/workspace-members');
    return response.items;
  }

  async switchWorkspace(workspaceId: string): Promise<AuthBootstrapResponse> {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, workspaceId);
    }
    this.clearCachedContext();
    this.configureApiClient();
    const context = await this.bootstrap();
    if (!context) throw new Error('Workspace switch returned no context.');
    return context;
  }

  getCachedContext(): AuthBootstrapResponse | null {
    if (this.bootstrappedContext) {
      return this.bootstrappedContext;
    }

    if (typeof window === 'undefined') {
      return null;
    }

    const serialized = window.localStorage.getItem(AUTH_CONTEXT_STORAGE_KEY);
    if (!serialized) {
      return null;
    }

    try {
      this.bootstrappedContext = JSON.parse(serialized) as AuthBootstrapResponse;
      return this.bootstrappedContext;
    } catch (error) {
      console.warn('Failed to parse cached auth context, discarding it.', error);
      window.localStorage.removeItem(AUTH_CONTEXT_STORAGE_KEY);
      return null;
    }
  }

  async bootstrap(): Promise<AuthBootstrapResponse | null> {
    const cachedContext = this.getCachedContext();
    if (cachedContext) {
      this.configureApiClient();
      if (hasServerBootstrapInputs()) {
        return cachedContext;
      }
      this.clearCachedContext();
    }

    if (!hasServerBootstrapInputs()) {
      return null;
    }

    this.configureApiClient();

    if (this.bootstrapPromise) {
      return this.bootstrapPromise;
    }

    this.bootstrapPromise = apiClient
      .post<AuthBootstrapResponse>('/auth/bootstrap', {})
      .then((context) => {
        this.bootstrappedContext = context;
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(AUTH_CONTEXT_STORAGE_KEY, JSON.stringify(context));
        }
        this.notifyAuthStateListeners(context);
        return context;
      })
      .catch((error) => {
        if (typeof window !== 'undefined') {
          window.localStorage.removeItem(AUTH_CONTEXT_STORAGE_KEY);
        }
        this.bootstrappedContext = null;
        this.notifyAuthStateListeners(null);
        throw error;
      })
      .finally(() => {
        this.bootstrapPromise = null;
      });

    return this.bootstrapPromise;
  }

  async ensureAuthenticatedContext(): Promise<AuthBootstrapResponse> {
    let context = await this.bootstrap();
    if (context) {
      return context;
    }

    if (typeof window !== 'undefined' && getGoogleClientId()) {
      context = await this.signInWithGoogle();
      return context;
    }

    throw new Error(
      'Frontend auth bootstrap is not configured. Set NEXT_PUBLIC_GOOGLE_CLIENT_ID, NEXT_PUBLIC_AUTH_TOKEN, or NEXT_PUBLIC_DEBUG_USER_EMAIL.',
    );
  }

  async isGoogleSignInAvailable(): Promise<boolean> {
    if (!getGoogleClientId() || typeof window === 'undefined') {
      return false;
    }

    await this.loadGoogleIdentityScript();
    return Boolean(window.google?.accounts?.id);
  }

  async renderGoogleSignInButton(container: HTMLElement): Promise<void> {
    const clientId = getGoogleClientId();
    if (!clientId || typeof window === 'undefined') {
      return;
    }

    await this.initializeGoogleIdentity();
    container.innerHTML = '';
    window.google?.accounts?.id?.renderButton(container, {
      theme: 'outline',
      size: 'large',
      shape: 'pill',
      text: 'signin_with',
      width: 260,
    });
  }

  async signInWithGoogle(): Promise<AuthBootstrapResponse> {
    const clientId = getGoogleClientId();
    if (!clientId || typeof window === 'undefined') {
      throw new Error('Google sign-in is not configured for this deployment.');
    }

    await this.initializeGoogleIdentity();

    return new Promise<AuthBootstrapResponse>((resolve, reject) => {
      const callback = async (response: { credential?: string }) => {
        if (!response.credential) {
          reject(new Error('Google sign-in did not return an identity token.'));
          return;
        }

        try {
          this.setBearerToken(response.credential);
          this.clearCachedContext();
          const context = await this.bootstrap();
          if (!context) {
            throw new Error('Authenticated bootstrap returned no user context.');
          }
          resolve(context);
        } catch (error) {
          reject(error);
        }
      };

      window.google?.accounts?.id?.initialize({
        client_id: clientId,
        callback,
        auto_select: false,
        cancel_on_tap_outside: true,
      });
      window.google?.accounts?.id?.prompt();
    });
  }

  signOut() {
    this.setBearerToken(null);
    this.clearCachedContext();
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(ACTIVE_WORKSPACE_STORAGE_KEY);
    }
    this.notifyAuthStateListeners(null);
    if (typeof window !== 'undefined') {
      window.google?.accounts?.id?.disableAutoSelect?.();
    }
  }

  clearCachedContext() {
    this.bootstrappedContext = null;
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(AUTH_CONTEXT_STORAGE_KEY);
    }
  }

  private async loadGoogleIdentityScript(): Promise<void> {
    if (typeof window === 'undefined') {
      return;
    }

    if (window.google?.accounts?.id) {
      return;
    }

    if (this.googleScriptPromise) {
      return this.googleScriptPromise;
    }

    this.googleScriptPromise = new Promise<void>((resolve, reject) => {
      const existingScript = document.getElementById(GOOGLE_IDENTITY_SCRIPT_ID) as HTMLScriptElement | null;
      if (existingScript) {
        existingScript.addEventListener('load', () => resolve(), { once: true });
        existingScript.addEventListener('error', () => reject(new Error('Failed to load Google Identity Services.')), { once: true });
        return;
      }

      const script = document.createElement('script');
      script.id = GOOGLE_IDENTITY_SCRIPT_ID;
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('Failed to load Google Identity Services.'));
      document.head.appendChild(script);
    });

    return this.googleScriptPromise;
  }

  private async initializeGoogleIdentity(): Promise<void> {
    const clientId = getGoogleClientId();
    if (!clientId || typeof window === 'undefined') {
      return;
    }

    await this.loadGoogleIdentityScript();
    if (!window.google?.accounts?.id || this.googleIdentityInitialized) {
      return;
    }

    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: ({ credential }) => {
        if (credential) {
          this.setBearerToken(credential);
          this.clearCachedContext();
          void this.bootstrap();
        }
      },
      auto_select: false,
      cancel_on_tap_outside: true,
    });
    this.googleIdentityInitialized = true;
  }

  private notifyAuthStateListeners(context: AuthBootstrapResponse | null) {
    this.authStateListeners.forEach((listener) => {
      listener(context);
    });
  }

  private configureApiClient() {
    const token = getConfiguredBearerToken();
    if (token) {
      apiClient.setToken(token);
    } else {
      apiClient.clearToken();
    }

    const workspaceId = getStoredWorkspaceId();
    apiClient.setDefaultHeaders({
      ...getConfiguredDebugHeaders(),
      ...(workspaceId ? { 'X-Workspace-Id': workspaceId } : {}),
    });
  }
}

export const authService = new AuthService();
