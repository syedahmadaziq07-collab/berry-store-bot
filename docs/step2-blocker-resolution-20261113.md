# Berry Store — STEP 2 blocker resolution audit (2026-11-13)

Staging branch audited: `origin/deploy/berry-ai-private-mapping-staging-20261111`
@ `942f24f` (PR #76 merged; all 9 CI PASS at 1338121, including actual SQL
snapshot worker integration). No duplicate of merged work is created here.

## 1. FAL_KEY format & authenticated connectivity
- **Root cause:** FAL_KEY is a Render-staging-only secret; this execution
  environment has NO key. Prior evidence (docs/evidence/
  staging-balance-readiness-20261113.json): key presence previously caused
  `credential_format_invalid` → after owner fixed the key in Render,
  **authenticated pricing GET returned HTTP 200 for all 3 models**.
- **Fix (already applied in production):** key format valid; earlier
  whitespace-normalization bug was fixed in prior merged PR.
- **Evidence:** pricing HTTP 200 × 3 (flux/schnell, wan a14b, minimax h3) —
  account-level inference authorization still UNVERIFIED (billing endpoint
  read returned **403**; `inference_access_verified: false`).
- **Remaining owner action:** none required for connectivity; 403 on
  billing/entitlement endpoints remains an owner/account-side matter.

## 2. MiniMax H3 Max Turbo 10s/480P verification
- **Root cause:** model/page config exists (playground defaults 768p; 480P
  selectable); documented billing = per second of generated video.
- **Fix:** configuration verified against official model page (fetched
  2026-11-13). Documented rates per second at 480p:
  USD 0.01625 (promo ≤ Oct 31), **USD 0.0175 (Nov 1–15 promo — matches the
  authenticated staging observation)**, **USD 0.025 standard from Nov 16**.
  Known ~0.7s output overrun documented; 10s requested ≠ ≤10 billed seconds.
- **Evidence:** PASS for pricing tiers/units (official page verbatim);
  FAIL for hard max billed seconds — provider gives no contractual bound.
- **Remaining owner action:** ask fal support for a hard max billable
  duration + rounding rule for 10s/480P, or accept the engineering
  worst-case bound (10.7s, documented overrun).

## 3. Pricing & RM1 net-margin retail price
- **Root cause:** mixing public vs authenticated rates; missing verified FX.
- **Fix (implemented, tested 7/7 — `tests/test_step2_minimax_retail_gate.py`):
  `minimum_retail_myr_cents()` fail-closed formula with documented rates:
  worst-case bound = unit_usd × max_seconds (incl. overrun); retail must
  cover bound×FX + fixed + RM1.00, divided by (1−fee), ceiled to RM0.02.
  Examples (FX 4.7, no fees): standard 480p 10s → **RM2.18 (218 sen,
  margin ≥ RM1 proven)**; 10.7s worst-case → higher; promo rate → RM1.84
  (not used for the gate — standard is the conservative bound).
- **Evidence:** 7/7 unit tests PASS including the ≥RM1 margin assertion and
  overrun-bound sensitivity.
- **Remaining owner action:** supply a verified conservative USD/MYR
  upper bound + fee fraction; approve the retail price before activation.

## 4. CI / staging integration
- All 9 CI workflows PASS at staging head 1338121 (recorded in merge of
  PR #76). This environment adds the retail-gate suite to
  `prod-step2-completion.yml`; full local suite OK.

## 5. Worker readiness / reconciliation / recovery
- Worker no-retry gate, SQL snapshot integration, recovery fairness, and
  reconciliation RPC all PASS in CI on the staging head (per merge note:
  "actual SQL snapshot worker integration"). Operator reconciliation facade
  remains unwired to a running daemon (owner-approved entry point needed).

## STEP 2 verdict
- Engineering: **complete on staging branch** (9/9 CI PASS).
- Runtime gates: pricing tiers verified (documented + authenticated match);
  **hard max billed seconds, account entitlement (billing 403), verified FX,
  and RM1-margin retail approval remain open** → STEP 2 stays **PARTIAL /
  NO-GO for paid generation**, consistent with all prior evidence.
- No paid calls made; no production or customer data touched; no duplicate
  PRs/migrations created.
