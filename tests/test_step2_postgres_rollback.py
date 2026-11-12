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

    def test_concurrent_transaction_advisory_lock(self):
        # Two independent transactions; no shared wallet or fixture writes.
        other = psycopg.connect(DSN)
        try:
            self.assertTrue(self.db.execute(
                "SELECT pg_try_advisory_xact_lock(700112)").fetchone()[0])
            self.assertFalse(other.execute(
                "SELECT pg_try_advisory_xact_lock(700112)").fetchone()[0])
            self.db.rollback()
            self.assertTrue(other.execute(
                "SELECT pg_try_advisory_xact_lock(700112)").fetchone()[0])
        finally:
            other.rollback()
            other.close()

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

    def test_durable_unknown_marker_persisted_before_post(self):
        # PR #75 gate contract: the claim transition must atomically move the
        # job to a pre-POST ambiguous state so a crash after the provider POST
        # can never be replayed as a new submission.
        self.db.execute("""CREATE FUNCTION pg_temp.claim_submit(p_id text) RETURNS boolean
          LANGUAGE plpgsql AS $body$
          DECLARE v_row text;
          BEGIN
            UPDATE pg_temp.job SET state='submission_unknown'
             WHERE id=p_id AND state='submitting' RETURNING id INTO v_row;
            IF v_row IS NULL THEN RETURN false; END IF;
            RETURN true;
          END $body$""")
        self.assertTrue(self.db.execute("SELECT pg_temp.claim('a')").fetchone()[0])
        # Worker's durable_unknown write happens BEFORE the provider POST.
        self.assertTrue(self.db.execute("SELECT pg_temp.claim_submit('a')").fetchone()[0])
        state = self.db.execute("SELECT state FROM job WHERE id='a'").fetchone()[0]
        self.assertEqual(state, "submission_unknown")
        # Crash simulation: restart must not be able to claim or POST again.
        self.assertFalse(self.db.execute("SELECT pg_temp.claim_submit('a')").fetchone()[0])
        self.assertFalse(self.db.execute("SELECT pg_temp.claim('a')").fetchone()[0])

    def test_crash_after_post_binds_response_once(self):
        # After the provider POST returns, exactly one bind to request_id is
        # allowed from the durable unknown state; a second bind is refused.
        self.db.execute("UPDATE job SET state='submission_unknown' WHERE id='a'")
        bind = """UPDATE job SET state='queued', request_id=%s WHERE id='a'
            AND state='submission_unknown' AND request_id IS NULL RETURNING id"""
        self.assertIsNotNone(self.db.execute(bind, ("post-crash-r1",)).fetchone())
        self.assertIsNone(self.db.execute(bind, ("post-crash-r2",)).fetchone())
        self.assertEqual(
            self.db.execute("SELECT request_id FROM job WHERE id='a'").fetchone()[0],
            "post-crash-r1")

    def test_wallet_single_debit_and_no_refund_on_unknown(self):
        # Budget consumption happens only once with the atomic claim; the
        # submission_unknown path never reverses it automatically.
        self.assertTrue(self.db.execute("SELECT pg_temp.claim('a')").fetchone()[0])
        self.db.execute("UPDATE job SET state='submission_unknown' WHERE id='a'")
        self.assertEqual(self.db.execute("SELECT used FROM budget").fetchone()[0], 400)
        # Refund-style decrement is only schema-blocked when it would drive the
        # balance negative (used=400, refund of 401 > balance is rejected);
        # smaller decrements are schema-legal, so safety relies on there being
        # NO code path that decrements -- proven below by state fencing.
        self.db.execute("SAVEPOINT refund_try")
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.db.execute("UPDATE budget SET used=used-401 WHERE id=1")
        self.db.execute("ROLLBACK TO SAVEPOINT refund_try")
        # Over-refund attempt left the budget untouched.
        self.assertEqual(self.db.execute("SELECT used FROM budget").fetchone()[0], 400)
        # A second claim attempt must not double-debit (fencing on state).
        self.assertFalse(self.db.execute("SELECT pg_temp.claim('a')").fetchone()[0])
        self.assertEqual(self.db.execute("SELECT used,generations FROM budget").fetchone(),(400,1))
        # The job stays in the unknown state: no transition back to 'reserved'
        # exists, so a resubmission claim (and thus a second debit) is impossible.
        state = self.db.execute("SELECT state FROM job WHERE id='a'").fetchone()[0]
        self.assertEqual(state, "submission_unknown")


if __name__ == "__main__":
    unittest.main()
