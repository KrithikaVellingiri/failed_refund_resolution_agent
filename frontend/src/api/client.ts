export const API_BASE = 'http://localhost:8000';

export async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errorBody = await res.json();
      if (errorBody && errorBody.detail) {
        errorDetail = typeof errorBody.detail === 'string' ? errorBody.detail : JSON.stringify(errorBody.detail);
      }
    } catch (e) {
      // Ignore JSON parse errors for non-JSON responses
    }
    const err = new Error(`API Error: ${res.status} ${errorDetail}`);
    (err as any).status = res.status;
    (err as any).detail = errorDetail;
    throw err;
  }
  
  return res.json();
}
