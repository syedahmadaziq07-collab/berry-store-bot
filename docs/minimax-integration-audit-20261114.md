# Berry Store — MiniMax integration audit (2026-11-14, new key era)

Audited against: official API schema page (fetched), production bot.py,
fal_provider.py, berry_admin_minimax_trial.py, berry_fal_authcheck.py (PR #88).

## 1. Authentication
- New key: read-only pricing auth probe `/falauth` (PR #88) returns
  `http_200` on success — owner verifies without exposing secrets.
- **Past 401 likely credential/permission-related:** old key produced HTTP 401; new key now
  configured and authenticated for read-only pricing GET only. Queue submit authentication still needs a fresh approved test. Prior key-format validation exists in
  `FalProvider._headers` (strict control-char validation, secret never
  logged; errors carry only fixed numeric codes, e.g. `http_401`).
- **Evidence:** `tests/test_minimax_contract.py` asserts error codes carry
  no key material; staging JSON shows HTTP 200 × 3 pricing reads previously.

## 2. Model endpoint & payload vs OFFICIAL schema (verified 2026-11-14)
- Endpoint: `POST https://queue.fal.run/minimax/h3-max-turbo/text-to-video`
  — matches `FalProvider.submit` exactly.
- Payload produced by `mini_max_arguments`: `{prompt, duration: 10,
  resolution: "480P", prompt_expansion_mode: "balanced",
  aspect_ratio: "16:9", enable_safety_checker: true}` — **all fields exist
  in the official schema with valid enum values** (resolution enum
  480P/768P/1080P; expansion disabled/balanced/quality; ratio enum incl.
  16:9). Duration is float-typed per schema; 10 is valid.
- **Evidence:** `tests/test_minimax_contract.py` (5/5) — parameter enum
  conformance, exact POST method+URL+JSON body, untrusted-host rejection,
  `http_401`-style coded errors.

## 3. Queue handling / polling / delivery
- Submit returns request_id + status/result URLs; `queue_urls` binds both to
  the model+request. Polling: bounded 600s, 5s interval, identity check
  `request_id` match, IN_QUEUE/IN_PROGRESS continue, COMPLETED+error → held.
- Delivery: `trusted_result_url` (fal.media hosts only), sendVideo ack with
  chat/message validation, token never logged; single-process duplicate prevention uses
  a local `O_EXCL` checkpoint before POST. Render Free filesystem persistence
  across redeploy or instances is not guaranteed.
- **Evidence:** test_admin_minimax_trial.py PASS (incl. retry-block and
  restart-persistence), test_telegram_video_delivery.py PASS.

## 4. Billing
- Billing = per second of generated video; output can overrun ~0.7s.
  Documented 480p rates: 0.01625 (≤Oct 31), 0.0175 (Nov 1–15), **0.025
  standard from Nov 16 2026**. Actual billing after a run is read from
  fal.ai Usage by the owner (the trial does not auto-read billing).
- Retail gate: `minimum_retail_myr_cents` (7/7 tests) — standard 480p 10s
  baseline at FX 4.7 → approximately RM2.18 retail if cost is exactly
  USD0.25 and before overhead. Minimum RM1 *net* margin is NOT proven;
  actual billed seconds, FX, payment fees and other costs remain unverified.

## 5. Integration limitations / remaining verification
- No blocker identified by offline tests. Production paid queue submission,
  polling, delivery and bill reconciliation are NOT yet verified. Two hardening
  observations covered by existing
  code: coded provider errors (no raw response), and prompt-expansion
  "balanced" adds ~1s latency before inference (accounted by 600s poll cap).

## 6. Duration mismatch investigation (request 01a1d621-ccf9-7c83-85bb-8e9b2ec89408)

Owner-verified facts:
- Payload requested `duration: 10` (matches official schema; 10 is valid).
- fal.ai billing: **USD 0.18, quantity 10.00 seconds → provider BILLED 10s**.
- Telegram playback observed: ~5 seconds.

### Root-cause procedure (encoded in `minimax_duration_audit.py`, 6/6 tests)
The original provider output can be re-fetched with a FREE read-only GET of
the existing request result (no new generation), then both files measured
with `ffprobe -show_entries format=duration`:
1. original provider file (v3b.fal.media URL from the result JSON)
2. the Telegram-delivered copy

`compare_durations()` classifies the verdict once both are measured:
- original ≈ billed (±1s) but Telegram ≉ original →
  `telegram_delivery_or_playback` (fix: sendVideo original bytes /
  document, validate duration before DELIVERED)
- original ≉ billed → `provider_output_short` (fix: escalate to fal
  support with request_id + both ffprobe outputs; **do NOT retry**;
  billing reconciliation hold)

### Evidence-based analysis (without re-fetching)
- Provider **billed 10.00 seconds** — fal bills per generated second, so the
  billed quantity is strong evidence the provider generated ~10s of video.
- A 10s 480p H3 clip is typically ~3–6MB (earlier probe fixture showed a
  768p sample at 3.3MB for 5s) — file_size in the original result JSON is a
  secondary cross-check.
- Most probable cause: **Telegram playback/preview** (client-side preview
  trim or player behavior), not the provider. This matches the owner's
  observation that Telegram metadata showed ~5s while billing says 10s.

### Required owner action (5 minutes, no cost)
Run the two ffprobe commands on the original fal.media URL (free GET) and
the Telegram-downloaded copy, then paste both durations — the classifier
returns the definitive root cause.

### Validation improvement (implemented)
`minimax_duration_audit.compare_durations` + tests: any future delivery
flow can reject/hold a job whose delivered-media duration diverges from the
original by >1s, and escalate provider-short outputs for billing
reconciliation instead of marking DELIVERED.
