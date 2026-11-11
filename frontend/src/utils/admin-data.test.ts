import test from 'node:test';
import assert from 'node:assert/strict';
import {loadAdminModules, MODULE_ENDPOINTS, MENU_REQUIREMENTS, pageFromPath} from './admin-data';

function validData(path: string) {
  if (path.endsWith('/dashboard/overview')) return {kpis: {totalRevenue: 0}, revenueTrend: []};
  if (path.endsWith('/wallet')) return {wallets: [], transactions: [], totalBalance: 0};
  if (path.endsWith('/bot-settings') || path.endsWith('/system/health')) return {};
  return [];
}

test('Each menu declares its backend dependencies and supports a deep link', () => {
  for (const menu of Object.keys(MENU_REQUIREMENTS)) {
    assert.equal(pageFromPath(menu === 'dashboard' ? '/dashboard' : `/dashboard/${menu}`), menu);
    for (const id of MENU_REQUIREMENTS[menu as keyof typeof MENU_REQUIREMENTS]) assert.ok(MODULE_ENDPOINTS[id]);
  }
  assert.equal(pageFromPath('/dashboard/not-a-page'), 'dashboard');
});

test('One disconnected module does not discard successful modules', async () => {
  const fetcher = (async (path: string) => {
    if (path.endsWith('/shop/categories')) throw new Error('network unavailable');
    return Response.json(validData(path));
  }) as typeof fetch;
  const results = await loadAdminModules(fetcher);
  assert.equal(results.categories?.status, 'error');
  assert.equal(results.products?.status, 'ready');
  assert.equal(results.orders?.status, 'ready');
  assert.equal(Object.keys(results).length, Object.keys(MODULE_ENDPOINTS).length);
});

test('Server errors remain errors rather than verified empty rows', async () => {
  const results = await loadAdminModules((async () => Response.json({error: 'Supabase not configured'}, {status: 503})) as typeof fetch);
  for (const result of Object.values(results)) {
    assert.equal(result?.status, 'error');
    if (result?.status === 'error') { assert.equal(result.httpStatus, 503); assert.equal(result.error, 'Supabase not configured'); }
    assert.ok(!('data' in result!));
  }
});

test('Expired authentication is distinguishable from empty store data', async () => {
  const results = await loadAdminModules((async () => Response.json({error: 'Authentication required'}, {status: 401})) as typeof fetch);
  for (const result of Object.values(results)) {
    assert.equal(result?.status, 'error');
    if (result?.status === 'error') assert.equal(result.httpStatus, 401);
  }
});

test('Malformed JSON and broken wallet/analytics contracts fail independently', async () => {
  const results = await loadAdminModules((async (path: string) => {
    if (path.endsWith('/orders')) return new Response('<html>error</html>');
    if (path.endsWith('/wallet')) return Response.json({wallets: [], totalBalance: 0});
    if (path.endsWith('/dashboard/overview')) return Response.json({kpis: {}});
    return Response.json(validData(path));
  }) as typeof fetch);
  assert.equal(results.orders?.status, 'error');
  assert.equal(results.wallet?.status, 'error');
  assert.equal(results.overview?.status, 'error');
  assert.equal(results.products?.status, 'ready');
});

test('All reads use same-origin cookies and propagate cancellation', async () => {
  const controller = new AbortController();
  controller.abort();
  const results = await loadAdminModules((async (_, init) => {
    assert.equal(init?.credentials, 'same-origin');
    assert.equal(init?.signal, controller.signal);
    throw new DOMException('Aborted', 'AbortError');
  }) as typeof fetch, controller.signal);
  assert.ok(Object.values(results).every(r => r?.status === 'error' && r.error.includes('masa')));
});
