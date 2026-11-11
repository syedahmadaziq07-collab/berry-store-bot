import { MutationKeys } from './utils/idempotency';
const mutationKeys = new MutationKeys();
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
  let fingerprint = '';
  if (mutating) {
    const bytes = new TextEncoder().encode(`${method}:${path}:${typeof init.body === 'string' ? init.body : ''}`);
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    fingerprint = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
    headers.set('Idempotency-Key', mutationKeys.acquire(fingerprint, () => crypto.randomUUID()));
  }
  const res = await fetch(path, {...init, headers, credentials: 'same-origin'});
  if (mutating) mutationKeys.settle(fingerprint, res.status);
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
