import { apiClient } from './apiClient';

export type WorkspaceRole = 'owner' | 'editor' | 'viewer';

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

const AUTH_CONTEXT_STORAGE_KEY = 'globesync.auth_context';
const AUTH_TOKEN_STORAGE_KEY = 'globesync.auth_token';

function readWindowStorage(key: string): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const value = window.localStorage.getItem(key);
  return value && value.trim().length > 0 ? value.trim() : null;
}

function getConfiguredBearerToken(): string | null {
  const envToken = process.env.NEXT_PUBLIC_AUTH_TOKEN?.trim();
  if (envToken) {
    return envToken;
  }

  return readWindowStorage(AUTH_TOKEN_STORAGE_KEY);
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

function hasBootstrapInputs(): boolean {
  return Boolean(getConfiguredBearerToken() || getConfiguredDebugHeaders()['X-Debug-User-Email']);
}

export class AuthService {
  private bootstrapPromise: Promise<AuthBootstrapResponse | null> | null = null;
  private bootstrappedContext: AuthBootstrapResponse | null = null;

  hasBootstrapConfig(): boolean {
    return Boolean(this.getCachedContext() || hasBootstrapInputs());
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
      return cachedContext;
    }

    if (!hasBootstrapInputs()) {
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
        return context;
      })
      .catch((error) => {
        if (typeof window !== 'undefined') {
          window.localStorage.removeItem(AUTH_CONTEXT_STORAGE_KEY);
        }
        this.bootstrappedContext = null;
        throw error;
      })
      .finally(() => {
        this.bootstrapPromise = null;
      });

    return this.bootstrapPromise;
  }

  async ensureAuthenticatedContext(): Promise<AuthBootstrapResponse> {
    const context = await this.bootstrap();
    if (!context) {
      throw new Error(
        'Frontend auth bootstrap is not configured. Set NEXT_PUBLIC_AUTH_TOKEN or NEXT_PUBLIC_DEBUG_USER_EMAIL.',
      );
    }
    return context;
  }

  clearCachedContext() {
    this.bootstrappedContext = null;
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(AUTH_CONTEXT_STORAGE_KEY);
    }
  }

  private configureApiClient() {
    const token = getConfiguredBearerToken();
    if (token) {
      apiClient.setToken(token);
    } else {
      apiClient.clearToken();
    }

    apiClient.setDefaultHeaders(getConfiguredDebugHeaders());
  }
}

export const authService = new AuthService();
