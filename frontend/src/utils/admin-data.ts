/** Module contracts: a failed request is never an empty successful dataset. */
export const MODULE_ENDPOINTS = {
  overview: '/dashboard/overview', products: '/shop/products', categories: '/shop/categories',
  orders: '/orders', credentials: '/credentials', customers: '/customers',
  tools: '/ai/tools', models: '/ai/models', wallet: '/wallet', settings: '/bot-settings',
  broadcasts: '/broadcast', audit: '/system/audit-logs', health: '/system/health',
} as const;
export type ModuleId = keyof typeof MODULE_ENDPOINTS;
export type ModuleResult = { status: 'ready'; data: unknown; checkedAt: string } |
  { status: 'error'; error: string; httpStatus?: number } | { status: 'loading' };
export type ModuleResults = Partial<Record<ModuleId, ModuleResult>>;
export const MENU_REQUIREMENTS = {
  dashboard: ['overview', 'orders', 'products'], shop: ['products'], orders: ['orders'],
  credentials: ['credentials', 'products'], customers: ['customers'],
  'ai-studio': ['tools'], 'ai-models': ['models'], wallets: ['wallet'],
  'bot-settings': ['settings'], broadcast: ['broadcasts', 'customers'],
  referrals: ['customers', 'settings'], monitoring: ['health'],
} as const;
export const MENU_OPTIONAL = {shop: ['categories'], 'ai-studio': ['models'], 'ai-models': ['tools'], monitoring: ['audit']} as const;
export type MenuId = keyof typeof MENU_REQUIREMENTS;
const arrays = new Set<ModuleId>(['products', 'categories', 'orders', 'credentials', 'customers', 'tools', 'models', 'broadcasts', 'audit']);

export async function loadAdminModules(fetcher: typeof fetch = fetch, signal?: AbortSignal): Promise<ModuleResults> {
  const entries = await Promise.all(Object.entries(MODULE_ENDPOINTS).map(async ([name, path]) => {
    const id = name as ModuleId;
    try {
      const response = await fetcher('/api/admin/v1' + path, {credentials: 'same-origin', signal});
      const data = await response.json().catch(() => null);
      if (!response.ok) return [id, {status: 'error', error: data?.error || `HTTP ${response.status}`, httpStatus: response.status}] as const;
      if (data === null || (arrays.has(id) ? !Array.isArray(data) : typeof data !== 'object' || Array.isArray(data))) {
        return [id, {status: 'error', error: 'Format data backend tidak sah'}] as const;
      }
      if (id === 'overview' && (!data.kpis || !Array.isArray(data.revenueTrend))) {
        return [id, {status: 'error', error: 'Kontrak analytics backend tidak lengkap'}] as const;
      }
      if (id === 'wallet' && (!Array.isArray(data.wallets) || !Array.isArray(data.transactions) || !Number.isFinite(data.totalBalance))) {
        return [id, {status: 'error', error: 'Kontrak wallet backend tidak lengkap'}] as const;
      }
      return [id, {status: 'ready', data, checkedAt: new Date().toISOString()}] as const;
    } catch (error) {
      return [id, {status: 'error', error: signal?.aborted ? 'Permintaan dibatalkan atau tamat masa' : 'Sambungan backend gagal'}] as const;
    }
  }));
  return Object.fromEntries(entries) as ModuleResults;
}

export function pageFromPath(path: string): MenuId {
  const name = path.replace(/^\/dashboard\/?/, '').replace(/\/$/, '');
  return Object.hasOwn(MENU_REQUIREMENTS, name) ? name as MenuId : 'dashboard';
}
