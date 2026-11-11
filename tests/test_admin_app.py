"""Runtime tests for the isolated Gemini Python host (no Telegram imports)."""
import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from werkzeug.security import generate_password_hash
from admin_app import BackendUnavailable, COOKIE, COLUMNS, DataStore, create_app, overview

BASE = 'https://admin.test'
API = '/api/admin/v1'
TENANT = '92c1e5ca-8498-438f-b777-3dc1c3195c1b'


class StoreFixture:
    """Explicit test fixture only. Never loaded by application runtime."""
    def __init__(self):
        self.calls = []
        self.rows = {table: [] for table in COLUMNS}
        self.rows['products'] = [{'id': 1, 'name': 'Fixture', 'price': '12.50', 'stock': 2, 'is_active': True}]
        self.rows['product_variants'] = [{'id': 3, 'product_id': 1, 'price': '15.00', 'stock': 4, 'variant_name': 'Month'}]
        self.rows['credentials'] = [{'id': 4, 'product_id': 1, 'variant_id': 3, 'is_used': False}]
        self.rows['users'] = [{'id': 7, 'username': 'fixture', 'first_name': 'Fixture', 'total_spent': '12.50'}]
        self.rows['orders'] = [{'id': 'ORD-1', 'user_id': 7, 'amount': '12.50', 'status': 'approved', 'created_at': '2026-11-11T01:00:00Z'}]
        self.rows['ai_wallets'] = [{'user_id': 7, 'balance': '3.00', 'currency': 'MYR'}]
        self.rows['bot_settings'] = [{'key': 'welcome_message', 'value': 'Hello'}, {'key': 'secret_provider_key', 'value': 'never-return'}]
    def configured(self):
        return True
    def read(self, table):
        self.calls.append(table)
        return copy.deepcopy(self.rows[table])
    def mutate(self, *args):
        self.calls.append(args)
        return {'id': 1}


class AdminSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash('test-password-only', method='pbkdf2:sha256:1000')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = StoreFixture()
        self.app = create_app({'TESTING': True, 'ADMIN_STATE_PATH': str(Path(self.tmp.name) / 'state.db'), 'ADMIN_PASSWORD_HASH': self.password_hash, 'DASHBOARD_ADMIN_SECRET': '', 'TENANT_ID': TENANT}, self.store)
        self.client = self.app.test_client()

    def login(self):
        response = self.client.post(API + '/auth/login', base_url=BASE, json={'password': 'test-password-only'})
        self.assertEqual(response.status_code, 200)
        self.csrf = response.json['csrfToken']
        return response

    def test_every_admin_read_requires_session(self):
        for path in ['auth/me', 'dashboard/overview', 'shop/products', 'shop/categories', 'orders', 'credentials', 'customers', 'wallet', 'referrals', 'bot-settings', 'ai/tools', 'ai/models', 'broadcast', 'system/health', 'system/audit-logs']:
            with self.subTest(path=path):
                response = self.client.get(API + '/' + path, base_url=BASE)
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.store.calls, [])

    def test_login_cookie_flags_and_no_password_in_response(self):
        response = self.login()
        cookie = response.headers['Set-Cookie']
        for flag in ['__Host-', 'HttpOnly', 'Secure', 'SameSite=Strict', 'Path=/']:
            self.assertIn(flag, cookie)
        self.assertNotIn('test-password-only', response.text)
        self.assertEqual(self.client.get(API + '/auth/me', base_url=BASE).json['user']['role'], 'admin')

    def test_logout_revokes_replayed_session(self):
        self.login()
        stolen = self.client.get_cookie(COOKIE, domain='admin.test').value
        self.assertEqual(self.client.post(API + '/auth/logout', base_url=BASE, headers={'X-CSRF-Token': self.csrf}).status_code, 200)
        self.client.set_cookie(COOKIE, stolen, domain='admin.test', secure=True)
        self.assertEqual(self.client.get(API + '/auth/me', base_url=BASE).status_code, 401)

    def test_csrf_and_origin_protection(self):
        self.login()
        for headers in [{}, {'X-CSRF-Token': 'wrong'}, {'X-CSRF-Token': self.csrf, 'Origin': 'https://evil.test'}]:
            self.assertEqual(self.client.post(API + '/auth/logout', base_url=BASE, headers=headers).status_code, 403)
        self.assertEqual(self.client.post(API + '/auth/login', base_url=BASE, json={'password': 'test-password-only'}, headers={'Origin': 'https://evil.test'}).status_code, 403)

    def test_login_rate_limit_survives_app_restart(self):
        for _ in range(8):
            self.assertEqual(self.client.post(API + '/auth/login', base_url=BASE, json={'password': 'wrong'}).status_code, 401)
        restarted = create_app(dict(self.app.config), self.store).test_client()
        response = restarted.post(API + '/auth/login', base_url=BASE, json={'password': 'test-password-only'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers['Retry-After'], '900')

    def test_login_payload_types_do_not_crash(self):
        for payload in [[], {'password': 123}, {'password': []}, {'password': None}]:
            self.assertEqual(self.client.post(API + '/auth/login', base_url=BASE, json=payload).status_code, 401)

    def test_all_mutations_locked_on_shared_database(self):
        self.login()
        for method, path in [('post', '/wallet/adjust'), ('patch', '/orders/ORD-1/status'), ('post', '/broadcast/send'), ('put', '/bot-settings'), ('post', '/shop/products'), ('post', '/credentials'), ('patch', '/customers/7/notes')]:
            response = getattr(self.client, method)(API + path, base_url=BASE, json={'tenant_id': 'other', 'role': 'superadmin'}, headers={'X-CSRF-Token': self.csrf})
            self.assertEqual(response.status_code, 423)
        self.assertFalse(any(isinstance(c, tuple) for c in self.store.calls))

    def test_read_adapters_return_real_field_contract(self):
        self.login()
        products = self.client.get(API + '/shop/products', base_url=BASE).json
        self.assertEqual(products[0]['id'], '1')
        self.assertEqual(products[0]['variants'][0]['price'], 15)
        customers = self.client.get(API + '/customers', base_url=BASE).json
        self.assertEqual(customers[0]['total_orders'], 1)
        self.assertEqual(customers[0]['wallet_balance'], 3)
        self.assertEqual(customers[0]['status'], 'unknown')
        self.assertEqual(self.client.get(API + '/wallet', base_url=BASE).json['totalBalance'], 3)

    def test_secrets_not_returned(self):
        self.login()
        response = self.client.get(API + '/credentials', base_url=BASE)
        self.assertNotIn('password', response.text)
        self.assertEqual(response.json[0]['credential_data'], '')
        settings = self.client.get(API + '/bot-settings', base_url=BASE).json
        self.assertEqual(settings, {'welcome_message': 'Hello'})

    def test_database_errors_are_visible_without_fake_success(self):
        self.login()
        with patch.object(self.store, 'read', side_effect=BackendUnavailable('Not configured')):
            response = self.client.get(API + '/shop/products', base_url=BASE)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json, {'error': 'Not configured'})
        self.assertEqual(self.client.get(API + '/broadcast', base_url=BASE).status_code, 501)
        self.assertEqual(self.client.get(API + '/ai/models/test/health', base_url=BASE).status_code, 501)

    def test_liveness_and_security_headers(self):
        response = self.client.get('/healthz', base_url=BASE)
        self.assertFalse(response.json['botPolling'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')

    def test_identity_cannot_be_changed_by_query_parameter(self):
        self.login()
        response = self.client.get(API + '/customers?tenant_id=other&role=owner', base_url=BASE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json[0]['id'], 7)

    def test_writes_need_isolation_and_idempotency(self):
        self.app.config['ADMIN_WRITES_ENABLED'] = True
        self.login()
        self.assertEqual(self.client.post(API + '/shop/products', base_url=BASE, headers={'X-CSRF-Token': self.csrf}).status_code, 423)
        self.app.config['ADMIN_ISOLATED_DATABASE'] = True
        self.assertEqual(self.client.post(API + '/shop/products', base_url=BASE, headers={'X-CSRF-Token': self.csrf}).status_code, 400)

    def test_invalid_product_cannot_reach_database(self):
        self.app.config.update(ADMIN_WRITES_ENABLED=True, ADMIN_ISOLATED_DATABASE=True)
        self.login()
        headers = {'X-CSRF-Token': self.csrf, 'Idempotency-Key': 'f61b0a6d-fc6d-4e20-9ca8-fc56c77ad727'}
        for body in [{'name': 'Test', 'price': -1}, {'name': 'Test', 'price': 'NaN'}, {'name': 'Test', 'price': 1, 'stock': True}, {'name': 'Test', 'price': 1, 'is_active': 'yes'}]:
            self.assertEqual(self.client.post(API + '/shop/products', base_url=BASE, headers=headers, json=body).status_code, 400)
        self.assertFalse(any(isinstance(c, tuple) for c in self.store.calls))

    def test_catalog_mutation_allowlist_ignores_tenant_injection(self):
        self.app.config.update(ADMIN_WRITES_ENABLED=True, ADMIN_ISOLATED_DATABASE=True)
        self.login()
        response = self.client.post(API + '/shop/products', base_url=BASE, headers={'X-CSRF-Token': self.csrf, 'Idempotency-Key': 'f61b0a6d-fc6d-4e20-9ca8-fc56c77ad727'}, json={'name': 'Test', 'price': '10.00', 'tenant_id': 'other', 'role': 'owner'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('tenant_id', self.store.calls[0][2])
        self.assertNotIn('role', self.store.calls[0][2])

    def test_all_connected_read_contracts_and_missing_schema_failures(self):
        self.login()
        paths = {'/shop/products': ['products', 'product_variants'], '/orders': ['orders'],
                 '/credentials': ['credentials'], '/shop/categories': ['categories'],
                 '/referrals': ['users'], '/bot-settings': ['bot_settings'],
                 '/customers': ['users', 'orders', 'ai_wallets'],
                 '/wallet': ['ai_wallets', 'ai_wallet_transactions'],
                 '/dashboard/overview': ['products', 'orders', 'ai_wallets']}
        for path, tables in paths.items():
            with self.subTest(path=path):
                self.store.calls.clear()
                self.assertEqual(self.client.get(API + path, base_url=BASE).status_code, 200)
                self.assertEqual(set(self.store.calls), set(tables))
                with patch.object(self.store, 'read', side_effect=BackendUnavailable('Schema unavailable')):
                    response = self.client.get(API + path, base_url=BASE)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json, {'error': 'Schema unavailable'})

    def test_ai_catalogue_fails_closed_without_isolated_configuration(self):
        self.login()
        for path in ('/ai/tools', '/ai/models'):
            with self.subTest(path=path):
                self.store.calls.clear()
                response = self.client.get(API + path, base_url=BASE)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(self.store.calls, [])

    def test_recent_orders_are_sorted_and_naive_dates_are_utc(self):
        self.store.rows['orders'].append({'id': 'ORD-2','status': 'pending','amount': 1,'created_at': '2026-11-12T01:00:00'})
        self.login()
        response = self.client.get(API + '/orders', base_url=BASE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['id'] for r in response.json], ['ORD-2', 'ORD-1'])
        self.assertEqual(response.json[0]['created_at'], '2026-11-12T01:00:00+00:00')

    def test_invalid_database_date_returns_visible_error(self):
        self.store.rows['orders'][0]['created_at'] = 'not-a-date'
        self.login()
        self.assertEqual(self.client.get(API + '/orders', base_url=BASE).status_code, 503)
        self.assertEqual(self.client.get(API + '/dashboard/overview', base_url=BASE).status_code, 503)

    def test_health_identifies_missing_server_configuration_without_secrets(self):
        self.login()
        response = self.client.get(API + '/system/health', base_url=BASE)
        self.assertEqual(response.json['configuration'], {'tenantConfigured': True, 'serverKeyConfigured': False})
        self.assertNotIn('test-password-only', response.text)


class DataStoreTests(unittest.TestCase):
    def test_pagination_and_tenant_scoping(self):
        seen = []
        def handler(request):
            seen.append(request)
            offset = int(request.url.params['offset'])
            return httpx.Response(200, json=[{'id': i} for i in range(offset, min(offset + 500, 661))])
        store = DataStore('https://project.supabase.co', 'test-key', TENANT, httpx.Client(transport=httpx.MockTransport(handler)))
        self.assertEqual(len(store.read('users')), 661)
        self.assertEqual(len(seen), 2)
        for request in seen:
            self.assertEqual(request.url.params['tenant_id'], 'eq.' + TENANT)
            self.assertNotIn('*', request.url.params['select'])
        self.assertEqual(seen[1].url.params['offset'], '500')

    def test_fail_closed_on_bad_tenant_url_or_table(self):
        for url, tenant in [('http://project.supabase.co', TENANT), ('https://evil.test', TENANT), ('https://project.supabase.co', '')]:
            with self.assertRaises(BackendUnavailable):
                DataStore(url, 'test-key', tenant).read('users')
        with self.assertRaises(BackendUnavailable):
            DataStore('https://project.supabase.co', 'test-key', TENANT).read('tenants')

    def test_error_response_does_not_expose_service_key(self):
        store = DataStore('https://project.supabase.co', 'very-secret', TENANT, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(403, json={'message': 'very-secret'}))))
        with self.assertRaises(BackendUnavailable) as ctx:
            store.read('users')
        self.assertNotIn('very-secret', str(ctx.exception))

    def test_analytics_uses_decimal_and_malaysia_day_boundary(self):
        data = overview([{'is_active': True, 'stock': 1}], [
            {'status': 'completed', 'amount': '0.10', 'created_at': '2026-11-10T16:30:00Z'},
            {'status': 'approved', 'amount': '0.20', 'created_at': '2026-11-11T01:00:00Z'},
            {'status': 'pending', 'amount': '100', 'created_at': '2026-11-11T01:00:00Z'},
        ], [{'balance': '3.50'}], datetime(2026, 11, 11, 2, tzinfo=timezone.utc))
        self.assertEqual(data['kpis']['totalRevenue'], .3)
        self.assertEqual(data['kpis']['revenueToday'], .3)
        self.assertEqual(data['kpis']['pendingOrdersCount'], 1)
        self.assertIsNone(data['kpis']['estimatedGrossProfit'])
        self.assertFalse(data['dataLimited'])

    def test_unsafe_supabase_url_configuration_fails_closed(self):
        for suffix in [':443', '/rest/v1', '?token=secret', '#fragment']:
            self.assertFalse(DataStore('https://project.supabase.co' + suffix, 'key', TENANT).configured())
        self.assertFalse(DataStore('https://user:secret@project.supabase.co', 'key', TENANT).configured())

    def test_unknown_transaction_result_is_not_success(self):
        for body in [[], {}, {'status': 'pending'}, {'error': 'not committed'}]:
            store = DataStore('https://project.supabase.co', 'secret-key', TENANT,
                httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))))
            with self.assertRaises(BackendUnavailable):
                store.mutate('product_stock', '1', {'stock': 1}, 'admin', 'key')

    def test_transaction_transport_error_is_sanitized_and_retry_aware(self):
        def handler(request):
            raise httpx.ReadTimeout('secret-key must not escape', request=request)
        store = DataStore('https://project.supabase.co', 'secret-key', TENANT,
            httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(BackendUnavailable) as error:
            store.mutate('product_stock', '1', {'stock': 1}, 'admin', 'key')
        self.assertNotIn('secret-key', str(error.exception))
        self.assertIn('idempotency key', str(error.exception))


if __name__ == '__main__':
    unittest.main()
