"""Real staging function snapshot compiled only in ephemeral PostgreSQL CI.

No Supabase connection, customer wallet or provider calls. A wallet-denying stub
prevents accidental debit/refund. Fixture database is discarded after CI.
"""
import concurrent.futures
import os
from pathlib import Path
import unittest
import uuid
try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    Jsonb = None

ROOT = Path(__file__).resolve().parents[1]
DSN = "postgresql://postgres:step2_local@127.0.0.1:5432/step2_clone"
TENANT = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
BUDGET = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))
QUOTE = {"all_in_cost_cents": 300, "provider_model_id": "fal-ai/wan/v2.2-a14b/text-to-video"}


@unittest.skipUnless(psycopg is not None and os.getenv("BERRY_STEP2_EPHEMERAL_CLONE") == "1", "ephemeral CI only")
class FullFunctionCloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.admin.execute((ROOT/"tests/fixtures/step2_ephemeral_schema.sql").read_text())
        cls.admin.execute((ROOT/"tests/fixtures/step2_live_function_snapshot.sql").read_text())
        cls.admin.execute("SELECT set_config('request.jwt.claims', %s, false)",
                          ('{"role":"service_role"}',))
        cls.original = cls.admin.execute(
            "SELECT pg_get_functiondef('public.berry_video_job(uuid,uuid,text,jsonb)'::regprocedure)"
        ).fetchone()[0]

    @classmethod
    def tearDownClass(cls):
        cls.admin.close()

    def setUp(self):
        self.job = str(uuid.uuid4())
        self.admin.execute("""INSERT INTO berry_private.ai_video_jobs
          (tenant_id,job_id,user_id,request_hash,arguments,quote,debit_cents,state)
          VALUES(%s,%s,99,repeat('a',64),'{}',%s,500,'reserved')""",
          (TENANT,self.job,Jsonb(QUOTE)))
        self.admin.execute("""INSERT INTO berry_private.ai_video_test_budgets
          (tenant_id,budget_id,test_user_id,max_cost_cents,max_generations,expires_at)
          VALUES(%s,%s,99,500,5,now()+interval '1 day')
          ON CONFLICT (tenant_id,budget_id) DO NOTHING""",(TENANT,BUDGET))

    def tearDown(self):
        self.admin.execute("DELETE FROM berry_private.ai_video_job_events WHERE tenant_id=%s AND job_id=%s",(TENANT,self.job))
        self.admin.execute("DELETE FROM berry_private.ai_video_jobs WHERE tenant_id=%s AND job_id=%s",(TENANT,self.job))
        self.admin.execute("UPDATE berry_private.ai_video_test_budgets SET reserved_cost_cents=0,reserved_generations=0 WHERE tenant_id=%s AND budget_id=%s",(TENANT,BUDGET))

    def call(self, action, payload=None):
        return self.admin.execute("SELECT public.berry_video_job(%s,%s,%s,%s)",
            (TENANT,self.job,action,Jsonb(payload or {}))).fetchone()[0]

    def test_claim_budget_and_duplicate_idempotency(self):
        first=self.call("claim_submit",{"budget_id":BUDGET})
        self.assertEqual(first["state"],"submitting")
        self.assertTrue(first["claimed"])
        second=self.call("claim_submit",{"budget_id":BUDGET})
        self.assertFalse(second["claimed"])
        used=self.admin.execute("SELECT reserved_cost_cents,reserved_generations FROM berry_private.ai_video_test_budgets WHERE tenant_id=%s AND budget_id=%s",(TENANT,BUDGET)).fetchone()
        self.assertEqual(used,(300,1))

    def test_budget_exhaustion_rolls_back_claim(self):
        self.admin.execute("UPDATE berry_private.ai_video_test_budgets SET reserved_cost_cents=400 WHERE tenant_id=%s AND budget_id=%s",(TENANT,BUDGET))
        with self.assertRaises(psycopg.Error):
            self.call("claim_submit",{"budget_id":BUDGET})
        self.assertEqual(self.call("get")["state"],"reserved")

    def test_ambiguous_recovery_migration_and_rollback(self):
        self.call("claim_submit",{"budget_id":BUDGET})
        self.call("submission_unknown")
        self.assertEqual(self.call("get")["state"],"submission_unknown")
        base="https://queue.fal.run/fal-ai/wan/requests/mock_r1"
        payload={"provider_request_id":"mock_r1","queue_result_url":base,"queue_status_url":base+"/status",
                 "recovery_mode":"operator_verified","recovery_request_hash":"a"*64,
                 "recovery_evidence":"verified manually from fake queue fixture"}
        with self.assertRaises(psycopg.Error):
            self.call("queued",payload)
        self.admin.execute((ROOT/"docs/sql/step2_video_unknown_recovery_staging_proposed.sql").read_text())
        with self.assertRaises(psycopg.Error):
            self.call("queued",payload | {"recovery_request_hash":"b"*64})
        result=self.call("queued",payload)
        self.assertEqual(result["state"],"queued")
        self.assertEqual(result["provider_request_id"],"mock_r1")
        self.assertEqual(self.call("queued",payload)["state"],"queued")
        self.admin.execute((ROOT/"docs/sql/step2_video_unknown_recovery_staging_rollback.sql").read_text())
        restored=self.admin.execute("SELECT pg_get_functiondef('public.berry_video_job(uuid,uuid,text,jsonb)'::regprocedure)").fetchone()[0]
        self.assertEqual(restored,self.original)

    def test_concurrent_claims_same_budget(self):
        other_job=str(uuid.uuid4())
        self.admin.execute("""INSERT INTO berry_private.ai_video_jobs
          (tenant_id,job_id,user_id,request_hash,arguments,quote,debit_cents,state)
          VALUES(%s,%s,99,repeat('b',64),'{}',%s,500,'reserved')""",
          (TENANT,other_job,Jsonb(QUOTE)))
        self.admin.execute("UPDATE berry_private.ai_video_test_budgets SET max_cost_cents=500 WHERE tenant_id=%s AND budget_id=%s",(TENANT,BUDGET))
        def claim(job):
            with psycopg.connect(DSN) as db:
                db.execute("SELECT set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)")
                try:
                    value=db.execute("SELECT public.berry_video_job(%s,%s,'claim_submit',%s)",
                                     (TENANT,job,Jsonb({"budget_id":BUDGET}))).fetchone()[0]
                    return value["state"]
                except psycopg.Error:
                    return "rejected"
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(claim,(self.job,other_job)))
            self.assertCountEqual(results,["submitting","rejected"])
            used=self.admin.execute("SELECT reserved_cost_cents,reserved_generations FROM berry_private.ai_video_test_budgets WHERE tenant_id=%s AND budget_id=%s",(TENANT,BUDGET)).fetchone()
            self.assertEqual(used,(300,1))
        finally:
            self.admin.execute("DELETE FROM berry_private.ai_video_job_events WHERE tenant_id=%s AND job_id=%s",(TENANT,other_job))
            self.admin.execute("DELETE FROM berry_private.ai_video_jobs WHERE tenant_id=%s AND job_id=%s",(TENANT,other_job))

    def test_service_role_fail_closed(self):
        self.admin.execute("SELECT set_config('request.jwt.claims','{}',false)")
        try:
            with self.assertRaises(psycopg.Error):
                self.call("get")
        finally:
            self.admin.execute("SELECT set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)")

    def test_wallet_stub_blocks_reserve(self):
        # Remove the pre-seeded reserved job so this call reaches the wallet stub.
        self.admin.execute(
            "DELETE FROM berry_private.ai_video_jobs WHERE tenant_id=%s AND job_id=%s",
            (TENANT, self.job),
        )
        quote={"debit_cents":500,"all_in_cost_cents":300,"credits":6250,
               "tool_key":"video","provider_model_id":"fal-ai/wan",
               "cost_reference":"fake","mapping_revision":1}
        with self.assertRaisesRegex(psycopg.Error, "wallet fixture forbidden"):
            self.call("reserve",{"user_id":99,"request_hash":"a"*64,
                "arguments":{},"quote":quote})


if __name__=="__main__":
    unittest.main()
