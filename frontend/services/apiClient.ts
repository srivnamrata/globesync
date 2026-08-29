export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

function getErrorMessage(errData: any, status: number): string {
  if (typeof errData?.message === 'string' && errData.message.length > 0) {
    return errData.message;
  }

  if (typeof errData?.detail === 'string' && errData.detail.length > 0) {
    return errData.detail;
  }

  if (typeof errData?.error?.message === 'string' && errData.error.message.length > 0) {
    return errData.error.message;
  }

  return `HTTP error! Status: ${status}`;
}

export class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = '/api/v1') {
    this.baseUrl = baseUrl;
  }

  setToken(token: string) {
    this.token = token;
  }

  async request<T>(
    endpoint: string,
    options: RequestInit = {},
    retries: number = 3,
    delayMs: number = 1000
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    // Default headers
    const headers = new Headers(options.headers || {});
    headers.set('Accept', 'application/json');
    if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`);
    }

    const config: RequestInit = {
      ...options,
      headers,
    };

    try {
      const response = await fetch(url, config);

      if (!response.ok) {
        // Retry logic on temporary server overloading (429 or 503)
        if ((response.status === 429 || response.status === 503) && retries > 0) {
          console.warn(`API Overloaded (${response.status}). Retrying in ${delayMs}ms...`);
          await new Promise((resolve) => setTimeout(resolve, delayMs));
          return this.request<T>(endpoint, options, retries - 1, delayMs * 2);
        }

        const errData = await response.json().catch(() => ({}));
        throw new ApiError(getErrorMessage(errData, response.status), response.status, errData);
      }

      return (await response.json()) as T;
    } catch (error: unknown) {
      if (retries > 0 && error instanceof Error && error.message.includes('Fetch failed')) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
        return this.request<T>(endpoint, options, retries - 1, delayMs * 2);
      }
      throw error;
    }
  }

  async get<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  async post<T>(endpoint: string, body: any, options?: RequestInit): Promise<T> {
    const isFormData = body instanceof FormData;
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: isFormData ? body : JSON.stringify(body),
    });
  }

  async put<T>(endpoint: string, body: any, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }

  async patch<T>(endpoint: string, body: any, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  async delete<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }
}

const resolvedApiBaseUrl = (() => {
  const configuredBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  return configuredBaseUrl.endsWith('/v1')
    ? configuredBaseUrl
    : `${configuredBaseUrl.replace(/\/$/, '')}/v1`;
})();

export const apiClient = new ApiClient(resolvedApiBaseUrl);
