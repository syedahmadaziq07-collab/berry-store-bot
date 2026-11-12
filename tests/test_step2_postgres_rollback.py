"""Dedicated local PostgreSQL fixture tests; never connect to Supabase.

Run only with BERRY_STEP2_LOCAL_POSTGRES=1 against ephemeral CI service.
All test mutations roll back and temp tables are session-local.
"""
import os
import pathlib
import unittest
try:
    import psycopg
except ImportError:
    psycopg = None

DSN = "postgresql://step2_test:step2_test@127.0.0.1:5432/step2_test"
ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(psycopg is not None and os.getenv("BERRY_STEP2_LOCAL_POSTGRES") == "1",
                     "requires ephemeral local PostgreSQL")
class PostgreSQLRollbackTests(unittest.TestCase):
    def setUp(self):
        self.db = psycopg.connect(DSN)
        self.db.execute("""CREATE TEMP TABLE budget(
            id integer PRIMARY KEY, cap integer NOT NULL CHECK(cap BETWEEN 1 AND 500),
            used integer NOT NULL DEFAULT 0 CHECK(used>=0),
            generations integer NOT NULL DEFAULT 0,
            max_generations integer NOT NULL CHECK(max_generations BETWEEN 1 AND 5),
            CHECK(used<=cap), CHECK(generations<=max_generations)) ON COMMIT DROP""")
        self.db.execute("""CREATE TEMP TABLE job(
            id text PRIMARY KEY, state text NOT NULL, request_hash text NOT NULL,
            request_id text UNIQUE, amount integer NOT NULL) ON COMMIT DROP""")
        self.db.execute("INSERT INTO budget(id,cap,max_generations) VALUES(1,500,2)")
        self.db.execute("""INSERT INTO job VALUES
            ('a','reserved',repeat('a',64),NULL,400),
            ('b','reserved',repeat('b',64),NULL,101)""")
        self.db.execute("""CREATE FUNCTION pg_temp.claim(p_id text) RETURNS boolean
          LANGUAGE plpgsql AS $body$
          DECLARE cost integer;
          BEGIN
            SELECT amount INTO cost FROM pg_temp.job WHERE id=p_id AND state='reserved' FOR UPDATE;
            IF NOT FOUND THEN RETURN false; END IF;
            UPDATE pg_temp.budget SET used=used+cost,generations=generations+1
             WHERE id=1 AND used+cost<=cap AND generations<max_generations;
            IF NOT FOUND THEN RETURN false; END IF;
            UPDATE pg_temp.job SET state='submitting' WHERE id=p_id;
            RETURN true;
          END $body$""")

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_atomic_claim_budget_exhaustion(self):
        self.assertTrue(self.db.execute("SELECT pg_temp.claim('a')").fetchone()[0])
        self.assertFalse(self.db.execute("SELECT pg_temp.claim('b')").fetchone()[0])
        self.assertEqual(self.db.execute("SELECT used,generations FROM budget").fetchone(),(400,1))

    def test_duplicate_claim_idempotency(self):
        self.assertTrue(self.db.execute("SELECT pg_temp.claim('a')").fetchone()[0])
        self.assertFalse(self.db.execute("SELECT pg_temp.claim('a')").fetchone()[0])
        self.assertEqual(self.db.execute("SELECT generations FROM budget").fetchone()[0],1)

    def test_hard_rm5_check_constraint(self):
        self.db.execute("SAVEPOINT cap")
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.db.execute("UPDATE budget SET cap=501 WHERE id=1")
        self.db.execute("ROLLBACK TO SAVEPOINT cap")
        self.assertEqual(self.db.execute("SELECT cap FROM budget").fetchone()[0],500)

    def test_ambiguous_recovery_binds_once(self):
        self.db.execute("UPDATE job SET state='submission_unknown' WHERE id='a'")
        sql = """UPDATE job SET state='queued',request_id=%s WHERE id='a'
           AND state='submission_unknown' AND request_id IS NULL
           AND request_hash=repeat('a',64) RETURNING id"""
        self.assertEqual(self.db.execute(sql,("mock_1",)).fetchone(),("a",))
        self.assertIsNone(self.db.execute(sql,("mock_2",)).fetchone())

    def test_migration_fingerprint_and_inverse_replace(self):
        migration = (ROOT/"docs/sql/step2_video_unknown_recovery_staging_proposed.sql").read_text()
        rollback = (ROOT/"docs/sql/step2_video_unknown_recovery_staging_rollback.sql").read_text()
        old = "ELSIF j.state='submitting' THEN\n      j.state:='queued'; j.provider_request_id:=v;"
        new = old+"\n    ELSIF j.state='submission_unknown'"
        fixture = "before\n"+old+"\nafter"
        changed = self.db.execute("SELECT replace(%s,%s,%s)",(fixture,old,new)).fetchone()[0]
        self.assertEqual(self.db.execute("SELECT replace(%s,%s,%s)",(changed,new,old)).fetchone()[0],fixture)
        self.assertIn("recovery_request_hash",migration)
        self.assertIn("j.provider_request_id IS NULL",migration)
        self.assertIn("expected staging function contract mismatch",migration)
        self.assertIn("expected migration fingerprint missing",rollback)


if __name__ == "__main__":
    unittest.main()
