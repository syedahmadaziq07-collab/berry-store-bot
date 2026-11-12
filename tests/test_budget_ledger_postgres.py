"""Isolated ephemeral PostgreSQL tests for the RM5 budget ledger SQL.

CI-only (BERRY_STEP3_LOCAL_POSTGRES=1), postgres:16 service. Never touches
Supabase. Verifies: RM5 ceiling CHECK, atomic claim reservation, concurrency
serialization, expiry, generation cap, service-role gate, wallet isolation.
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
END $$;
GRANT USAGE ON SCHEMA public TO service_role, anon;
GRANT USAGE ON SCHEMA berry_private TO service_role;
"""


def claims(db, role="service_role"):
    db.execute("SELECT set_config('request.jwt.claims', "
               "'{\"role\": \"%s\"}'::text, true)" % role)


@unittest.skipUnless(psycopg is not None and os.getenv("BERRY_STEP3_LOCAL_POSTGRES") == "1",
                     "requires ephemeral local PostgreSQL")
class BudgetLedgerPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(DSN)
        cls.db.execute("CREATE SCHEMA IF NOT EXISTS berry_private")
        cls.db.execute(ROLES_DDL)
        ddl = (ROOT / "docs/sql/berry_ai_test_budget.sql").read_text()
        cls.db.execute(ddl.replace("BEGIN;", "").replace("COMMIT;", ""))
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.execute("DROP FUNCTION IF EXISTS public.berry_ai_budget_claim(uuid,uuid,int,uuid)")
        cls.db.execute("DROP TABLE IF EXISTS berry_private.ai_test_budgets")
        cls.db.commit()
        cls.db.close()

    def setUp(self):
        claims(self.db)
        self.tenant = uuidmod.uuid4()
        self.budget = uuidmod.uuid4()
        self.db.execute("INSERT INTO public.tenants(id) VALUES (%s)", (self.tenant,))
        self.db.execute(
            "INSERT INTO berry_private.ai_test_budgets(tenant_id,budget_id,cap_cents,expires_at)"
            " VALUES(%s,%s,500,now()+interval '2 hours')", (self.tenant, self.budget))

    def tearDown(self):
        self.db.rollback()

    def claim(self, cost, job=None):
        return self.db.execute("SELECT public.berry_ai_budget_claim(%s,%s,%s,%s)",
                               (self.tenant, self.budget, cost, job or uuidmod.uuid4())
                               ).fetchone()[0]

    def test_cap_over_rm5_rejected_by_check(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.db.execute(
                "INSERT INTO berry_private.ai_test_budgets(tenant_id,budget_id,cap_cents,expires_at)"
                " VALUES(%s,%s,501,now()+interval '1 hour')",
                (self.tenant, uuidmod.uuid4()))

    def test_claim_reserves_atomically(self):
        self.assertTrue(self.claim(200))
        self.assertEqual(self.db.execute(
            "SELECT reserved_cents, generations FROM berry_private.ai_test_budgets"
            " WHERE budget_id=%s", (self.budget,)).fetchone(), (200, 1))

    def test_worst_case_over_remaining_rejected(self):
        self.assertTrue(self.claim(300))
        with self.assertRaises(psycopg.errors.RaiseException):
            self.claim(201)

    def test_generation_cap_enforced(self):
        for _ in range(5):
            self.assertTrue(self.claim(10))
        with self.assertRaises(psycopg.errors.RaiseException):
            self.claim(10)

    def test_expired_budget_rejects(self):
        self.db.execute("UPDATE berry_private.ai_test_budgets"
                        " SET expires_at=now()-interval '1 second' WHERE budget_id=%s",
                        (self.budget,))
        with self.assertRaises(psycopg.errors.RaiseException):
            self.claim(10)

    def test_concurrent_claims_serialize_within_cap(self):
        results = []
        lock = threading.Lock()

        def run():
            other = psycopg.connect(DSN)
            claims(other)
            try:
                ok = other.execute(
                    "SELECT public.berry_ai_budget_claim(%s,%s,%s,%s)",
                    (self.tenant, self.budget, 200, uuidmod.uuid4())).fetchone()[0]
                other.commit()
                with lock:
                    results.append(ok)
            except Exception:
                other.rollback()
                with lock:
                    results.append(False)
            finally:
                other.close()

        threads = [threading.Thread(target=run) for _ in range(3)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        self.assertEqual(results.count(True), 2)
        self.assertEqual(results.count(False), 1)
        reserved = self.db.execute(
            "SELECT reserved_cents FROM berry_private.ai_test_budgets"
            " WHERE budget_id=%s", (self.budget,)).fetchone()[0]
        self.assertEqual(reserved, 400)

    def test_anon_jwt_role_rejected(self):
        claims(self.db, "anon")
        with self.assertRaises(psycopg.errors.RaiseException):
            self.claim(10)

    def test_no_wallet_table_created(self):
        rows = self.db.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema='berry_private'").fetchall()
        self.assertIn("ai_test_budgets", [r[0] for r in rows])
        for name in [r[0] for r in rows]:
            self.assertNotIn("wallet", name)


if __name__ == "__main__":
    unittest.main()
