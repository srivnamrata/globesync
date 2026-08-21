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
        throw new Error(errData.message || `HTTP error! Status: ${response.status}`);
      }

      return (await response.json()) as T;
    } catch (error: any) {
      if (retries > 0 && error.message.includes('Fetch failed')) {
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

  async delete<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }
}

export const apiClient = new ApiClient(
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1'
);
