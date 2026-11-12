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

| 2026-11-12 | feat/step2-no-retry-worker-integration-20261112 | (this push) | `StagingJobWorker.submit` POST now routed through `WorkerSubmissionGate`: durable `submission_unknown` before POST, single POST, response binding, fail-closed hold. Safety upgraded: failed durable-marker write now prevents any POST. | worker 22/22, step2 60/60, video_myr 12/12, no_retry 6/6 OK locally | pending |

| 2026-11-12 | feat/step2-no-retry-worker-integration-20261112 | (this push) | `MyrVideoWorker.submit` routed through `WorkerSubmissionGate` (+5 regression tests); +3 ephemeral PostgreSQL 16 CI fixtures for durable-unknown-before-POST fencing, crash-after-POST single binding, wallet single debit/no auto refund; CI workflow extended to run all four gate suites. | video_myr 17/17, staging 22/22, step2 63/63 local (15 CI-only skips) | pending |

| 2026-11-12 | feat/step2-no-retry-worker-integration-20261112 | (this push) | Restricted operator reconciliation (allowlist, pre-read authorization, append-only audit, no refund/resubmit) + read-only fal pricing probe (allowlisted origins only, fail-closed on invalid responses, cost-bound verification with server FX); +18 tests; unused import cleanup after final review. | ops-recon 7/7, pricing 11/11, step2 81/81, video 17/17, staging 22/22 local | pending |

| 2026-11-12 | feat/step2-no-retry-worker-integration-20261112 | (this push) | Staging E2E preflight module (+5 tests, fail-closed, RM5 ceiling); fal pricing docs audit (billing units confirmed; Platform pricing endpoint schema UNVERIFIED — documented as assumption); mock-vs-real evidence classification; operator reconciliation wiring audit; full STEP 2 acceptance matrix with exact blockers. | step2 86/86 local (15 CI-only skips) | pending |

PR creation: `gh` CLI not installed and no GitHub API token in this environment.
PR target branch: `deploy/berry-ai-private-mapping-staging-20261111`.
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