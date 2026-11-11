let csrfToken = '';
export function setCsrfToken(token: string) { csrfToken = token; }
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method || 'GET').toUpperCase();
  const mutating = !['GET', 'HEAD', 'OPTIONS'].includes(method);
  if (mutating && !path.endsWith('/auth/login') && !path.endsWith('/auth/logout')) {
    if (!window.confirm('Sahkan tindakan ini? Perubahan hanya dibenarkan apabila backend membenarkannya.')) {
      throw new Error('Tindakan dibatalkan');
    }
  }
  const headers = new Headers(init.headers);
  if (mutating && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  if (mutating) headers.set('Idempotency-Key', crypto.randomUUID());
  const res = await fetch(path, {...init, headers, credentials: 'same-origin'});
  if (!res.ok) {
    const data = await res.clone().json().catch(() => ({}));
    const error = new Error(data.error || `Permintaan gagal (${res.status})`);
    if (res.status === 401 && !path.endsWith('/auth/login') && !path.endsWith('/auth/me')) {
      window.dispatchEvent(new Event('session-expired'));
    }
    if (mutating) window.dispatchEvent(new CustomEvent('api-error', {detail: error.message}));
    throw error;
  }
  return res;
}
