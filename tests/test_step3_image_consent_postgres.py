"""STEP 3 — isolated ephemeral PostgreSQL 16 tests for image consent SQL.

Runs only with BERRY_STEP3_LOCAL_POSTGRES=1 against a CI service database
(the step2-postgres-rollback.yml pattern). Never connects to Supabase.
Installs the candidate DDL in isolated schemas, exercises the full lifecycle,
replay protection, ownership isolation, expiry, concurrency (advisory lock),
RLS/ACL denial and asserts zero unintended wallet debits (no wallet table
exists at all — debits are structurally impossible).
"""
import os
import pathlib
import threading
import unittest
import uuid as uuidmod

try:
    import psycopg
except ImportError:
    psycopg = None

DSN = "postgresql://step2_test:step2_test@127.0.0.1:5432/step2_test"
ROOT = pathlib.Path(__file__).resolve().parents[1]

ROLES_DDL = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
    CREATE ROLE service_role NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO service_role, anon, authenticated;
GRANT USAGE ON SCHEMA berry_private TO service_role;
"""


def tenant():
    return uuidmod.uuid4()


def service_claims(db):
    db.execute("SELECT set_config('request.jwt.claims','{\"role\":\"service_role\"}',true)")


PAYLOAD = {
    'user_id': 900000088, 'request_hash': 'b' * 64,
    'expires_at': '2099-01-01T00:00:00+00',
    'arguments': {'prompt': 'fixture', 'aspect_ratio': '1:1', 'num_images': 1},
    'quote': {'tool_key': 'image', 'provider_model_id': 'fal-ai/flux/schnell',
              'mapping_revision': 1, 'credits': 1325, 'debit_cents': 106,
              'all_in_cost_cents': 6, 'cost_reference': 'fixture only'}}


@unittest.skipUnless(psycopg is not None and os.getenv("BERRY_STEP3_LOCAL_POSTGRES") == "1",
                     "requires ephemeral local PostgreSQL")
class ImageConsentPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(DSN)
        cls.db.execute("CREATE SCHEMA IF NOT EXISTS berry_private")
        cls.db.execute(ROLES_DDL)
        ddl = (ROOT / "docs/sql/berry_image_consent.sql").read_text()
        cls.db.execute(ddl.replace("BEGIN;", "").replace("COMMIT;", ""))
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.execute(
            "DROP FUNCTION IF EXISTS public.berry_image_checkout(uuid,bigint,uuid,text,jsonb)")
        cls.db.execute("DROP TABLE IF EXISTS berry_private.ai_image_tickets")
        cls.db.execute("DROP SCHEMA IF EXISTS berry_private")
        cls.db.commit()
        cls.db.close()

    def setUp(self):
        service_claims(self.db)
        self.t = tenant()
        self.db.execute("INSERT INTO public.tenants(id) VALUES (%s)", (self.t,))

    def tearDown(self):
        self.db.rollback()

    def call(self, t, user, ticket, action, payload):
        return self.db.execute(
            "SELECT public.berry_image_checkout(%s,%s,%s,%s,%s::jsonb)",
            (t, user, ticket, action,
             psycopg.types.json.Jsonb(payload) if isinstance(payload, dict) else payload)
        ).fetchone()[0]

    def test_prepare_is_idempotent_and_pending(self):
        ticket = tenant()
        first = self.call(self.t, 900000088, ticket, 'prepare', PAYLOAD)
        second = self.call(self.t, 900000088, ticket, 'prepare', PAYLOAD)
        self.assertEqual(first['state'], 'pending')
        self.assertEqual(second['state'], 'pending')
        cnt = self.db.execute(
            "SELECT count(*) FROM berry_private.ai_image_tickets"
            " WHERE tenant_id=%s AND ticket_id=%s", (self.t, ticket)).fetchone()[0]
        self.assertEqual(cnt, 1)

    def test_replay_with_changed_payload_rejected(self):
        ticket = tenant()
        self.call(self.t, 900000088, ticket, 'prepare', PAYLOAD)
        changed = dict(PAYLOAD, request_hash='c' * 64)
        with self.assertRaises(psycopg.errors.RaiseException):
            self.call(self.t, 900000088, ticket, 'prepare', changed)

    def test_owner_mismatch_rejected(self):
        ticket = tenant()
        self.call(self.t, 900000088, ticket, 'prepare', PAYLOAD)
        with self.assertRaises(psycopg.errors.RaiseException):
            self.call(self.t, 900000089, ticket, 'get', {})

    def test_non_image_tool_key_rejected(self):
        ticket = tenant()
        bad = dict(PAYLOAD)
        bad['quote'] = dict(bad['quote'], tool_key='video')
        with self.assertRaises(psycopg.errors.RaiseException):
            self.call(self.t, 900000088, ticket, 'prepare', bad)

    def test_invalid_request_hash_rejected(self):
        ticket = tenant()
        bad = dict(PAYLOAD, request_hash='nothex')
        with self.assertRaises(psycopg.errors.RaiseException):
            self.call(self.t, 900000088, ticket, 'prepare', bad)

    def test_past_expiry_rejected_at_prepare(self):
        ticket = tenant()
        past = dict(PAYLOAD, expires_at='2000-01-01T00:00:00+00')
        with self.assertRaises(psycopg.errors.RaiseException):
            self.call(self.t, 900000088, ticket, 'prepare', past)

    def test_confirm_fail_closed_until_job_wiring(self):
        ticket = tenant()
        self.call(self.t, 900000088, ticket, 'prepare', PAYLOAD)
        with self.assertRaises(psycopg.errors.RaiseException) as cm:
            self.call(self.t, 900000088, ticket, 'confirm', {})
        self.assertIn('image job reservation not yet enabled', str(cm.exception))

    def test_cancel_then_confirm_rejected(self):
        ticket = tenant()
        self.call(self.t, 900000088, ticket, 'prepare', PAYLOAD)
        out = self.call(self.t, 900000088, ticket, 'cancel', {})
        self.assertEqual(out['state'], 'cancelled')
        with self.assertRaises(psycopg.errors.RaiseException) as cm:
            self.call(self.t, 900000088, ticket, 'confirm', {})
        self.assertIn('ticket cancelled', str(cm.exception))

    def test_expired_ticket_confirm_rejected(self):
        ticket = tenant()
        self.call(self.t, 900000088, ticket, 'prepare', PAYLOAD)
        self.db.execute(
            "UPDATE berry_private.ai_image_tickets SET expires_at=now()-interval '1 second'"
            " WHERE tenant_id=%s AND ticket_id=%s", (self.t, ticket))
        with self.assertRaises(psycopg.errors.RaiseException):
            self.call(self.t, 900000088, ticket, 'confirm', {})

    def test_concurrent_prepare_single_row(self):
        ticket = tenant()
        results = []
        lock = threading.Lock()

        def run():
            other = psycopg.connect(DSN)
            service_claims(other)
            try:
                out = other.execute(
                    "SELECT public.berry_image_checkout(%s,%s,%s,'prepare',%s::jsonb)",
                    (self.t, 900000088, ticket,
                     psycopg.types.json.Jsonb(PAYLOAD))).fetchone()[0]
                other.commit()
                with lock:
                    results.append(out['state'])
            except Exception:
                other.rollback()
            finally:
                other.close()

        threads = [threading.Thread(target=run) for _ in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        cnt = self.db.execute(
            "SELECT count(*) FROM berry_private.ai_image_tickets"
            " WHERE tenant_id=%s AND ticket_id=%s", (self.t, ticket)).fetchone()[0]
        self.assertEqual(cnt, 1)
        self.assertTrue(all(s == 'pending' for s in results))

    def test_wallet_isolation_no_debit_possible(self):
        rows = self.db.execute("""
            SELECT table_name FROM information_schema.tables
             WHERE table_schema='berry_private'""").fetchall()
        self.assertEqual([r[0] for r in rows], ['ai_image_tickets'])
        fn = self.db.execute("""
            SELECT count(*) FROM information_schema.routines
             WHERE routine_name LIKE '%wallet%'
               AND routine_schema IN ('public','berry_private')""").fetchone()[0]
        self.assertEqual(fn, 0)

    def test_public_acl_denied(self):
        priv = self.db.execute("""
            SELECT has_function_privilege('anon',
             'public.berry_image_checkout(uuid,bigint,uuid,text,jsonb)','EXECUTE')"""
        ).fetchone()[0]
        self.assertFalse(priv)


if __name__ == "__main__":
    unittest.main()

