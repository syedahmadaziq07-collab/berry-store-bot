# Berry Store — Master Progress (STEP 1–12)

Managed alongside `docs/BERRY_STORE_STEP2_PROGRESS.md`. Records verified commits,
tests, PRs, CI and deployment evidence only — no unverified claims.

## Status summary
- STEP 1: STAGING VERIFIED (see docs/evidence/step1-ai-audit-20261112.json).
- STEP 2: PARTIAL / NO-GO for paid generation. Highest-priority integration
  work in progress below.
- STEP 3–12: not started; roadmap recovery pending genuine STEP 2 PASS.

## STEP 2 engineering log
| Date | Branch | Commit | Change | Tests | CI |
|------|--------|--------|--------|-------|----|
| 2026-11-12 | feat/step2-no-retry-worker-integration-20261112 | 334040a | `step2_submission_gate.py` wires the PR #75 durable no-retry state machine as the sole sanctioned path to a single provider POST (durable SUBMISSION_UNKNOWN before POST, generation-fenced single authorization, response binding, restart → poll/hold, never a second POST). | `tests/test_step2_submission_gate.py` — 10/10 pass locally (Python 3.13), no network/DB/paid calls | `.github/workflows/step2-submission-gate.yml` added; pending first PR run |
| (prior) | deploy/berry-ai-private-mapping-staging-20261111 | fe99478 | PR #75 fail-closed durable no-retry submission protocol (reference state machine) | tests/test_step2_no_retry_protocol.py 6/6 | step2-durable-no-retry.yml |

PR creation: `gh` CLI not installed and no GitHub API token in this environment.
Open PR from: https://github.com/syedahmadaziq07-collab/berry-store-bot/pull/new/feat/step2-no-retry-worker-integration-20261112

## Safety boundaries honoured
- No production database or deployment modified.
- No paid fal.ai calls (mocked only).
- No customer wallet writes; no credentials exposed; no force-push.
- PR #70 unsafe recovery SQL not applied.

## Next tasks (STEP 2)
1. Refactor `StagingJobWorker.submit` and `video_myr_worker.VideoMyrWorker.submit`
   to route through `WorkerSubmissionGate` (keeps store-specific claim semantics).
2. Ephemeral-Postgres integration tests: crash before/after POST, timeout,
   concurrent claim, tenant isolation.
3. Restricted operator reconciliation route rejecting user-supplied proof.
4. Read-only account-specific fal pricing validation (no paid inference).
5. Gaps requiring explicit owner approval: staging migration, wallet writes,
   paid generation, Render deploy (see STEP2 checkpoint blockers).