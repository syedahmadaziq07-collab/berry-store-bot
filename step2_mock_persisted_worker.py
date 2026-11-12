"""Mock-only persisted video worker harness. Not imported by bot/admin runtime.

No provider HTTP client, no Supabase client, no wallet or customer API.
The injected transport is deliberately limited to a fake in-memory provider.
"""
import sqlite3
from step2_offline_queue_contract import classify_queue_status, QueueContractError


class WorkerBlocked(RuntimeError):
    pass


class MockWorker:
    def __init__(self, path, provider):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.provider = provider
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs(
            job_id TEXT PRIMARY KEY, state TEXT NOT NULL, request_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, reserved_cents INTEGER NOT NULL DEFAULT 0)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS budget(
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            cap_cents INTEGER NOT NULL CHECK(cap_cents BETWEEN 1 AND 500),
            reserved_cents INTEGER NOT NULL DEFAULT 0,
            generations INTEGER NOT NULL DEFAULT 0,
            max_generations INTEGER NOT NULL)""")

    def configure_budget(self, cap_cents, max_generations):
        if type(cap_cents) is not int or not 1 <= cap_cents <= 500 or type(max_generations) is not int or max_generations < 1:
            raise WorkerBlocked("invalid_budget")
        self.db.execute("INSERT INTO budget VALUES (1, ?, 0, 0, ?)", (cap_cents, max_generations))

    def create(self, job_id):
        self.db.execute("INSERT INTO jobs(job_id,state) VALUES (?, 'reserved')", (job_id,))

    def claim(self, job_id, cost_cents):
        if type(cost_cents) is not int or cost_cents <= 0:
            raise WorkerBlocked("invalid_cost")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None or row[0] != "reserved":
                raise WorkerBlocked("not_reservable")
            updated = self.db.execute("""UPDATE budget SET reserved_cents=reserved_cents+?,
                generations=generations+1 WHERE singleton=1
                AND reserved_cents+?<=cap_cents AND generations<max_generations""",
                (cost_cents, cost_cents)).rowcount
            if updated != 1:
                raise WorkerBlocked("budget_exhausted")
            self.db.execute("UPDATE jobs SET state='submitting', reserved_cents=? WHERE job_id=?",
                            (cost_cents, job_id))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def submit_once(self, job_id):
        row = self.db.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None or row[0] != "submitting":
            raise WorkerBlocked("not_submittable")
        # Mark unknown BEFORE outbound fake call. On crash, never blindly resubmit.
        self.db.execute("UPDATE jobs SET state='submission_unknown' WHERE job_id=?", (job_id,))
        try:
            request_id = self.provider.submit(job_id)
            if not isinstance(request_id, str) or not request_id:
                return "submission_unknown"
            self.db.execute("UPDATE jobs SET state='queued',request_id=? WHERE job_id=? AND state='submission_unknown'",
                            (request_id, job_id))
            return "queued"
        except Exception:
            return "submission_unknown"

    def poll_once(self, job_id, max_attempts=12):
        row = self.db.execute("SELECT state,request_id,attempts FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None or row[0] != "queued" or not row[1]:
            raise WorkerBlocked("not_pollable")
        try:
            status = self.provider.status(row[1])
            decision = classify_queue_status(status, request_id=row[1], attempt=row[2], max_attempts=max_attempts)
        except (Exception,):
            self.db.execute("UPDATE jobs SET state='needs_review' WHERE job_id=? AND state='queued'", (job_id,))
            return "needs_review"
        if decision.action == "fetch_result":
            self.db.execute("UPDATE jobs SET state='result_pending' WHERE job_id=? AND state='queued'", (job_id,))
            return "result_pending"
        self.db.execute("UPDATE jobs SET attempts=attempts+1 WHERE job_id=? AND state='queued'", (job_id,))
        return "queued"

    def state(self, job_id):
        return self.db.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()[0]

    def close(self):
        self.db.close()
