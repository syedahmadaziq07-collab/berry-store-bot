# MiniMax trial: investigation of first ambiguous submission

**Observed:** The owner confirmed FAL_KEY exists on production Render berry-store-bot-1,
but the first /videotest_confirm replied "Keputusan ujian belum disahkan"
with NO provider request ID. fal.ai MiniMax Requests UI showed no requests;
account credits displayed USD 10.00 at the time. Neither is conclusive proof
of non-billing or model inference permission.

**Source code root cause of unhelpful diagnosis:** The first version of
FalProvider._request collapses every HTTP error, timeout and JSON parse error into
"fal.ai request failed", while AdminMiniMaxTrial._generate collapses that again
into "Keputusan ujian belum disahkan". Consequently the original failure
HTTP status/code was NOT recorded and cannot be recovered from Render logs.

**Read-only improvement:** New /videotest_diag performs ONLY GET
https://api.fal.ai/v1/models/pricing?endpoint_id=minimax/h3-max-turbo/text-to-video
using the server's existing FAL_KEY. Admin/private chat authorization is
unchanged. It returns a sanitized HTTP status, invalid_response or timeout code.
Successful pricing GET confirms this service's key works for pricing metadata,
not inference entitlement.

**Paid retry interlock:** After this patch, /videotest_confirm REQUIRES
BERRY_MINIMAX_TRIAL_PAID_ENABLED=true, otherwise refuses before any POST.
Do NOT set this variable until the previous request/usage has been reconciled,
and a new spend is explicitly authorized. No automatic POST retry is added.
The old attempt state was kept in a local /tmp checkpoint, which might have
disappeared when Render manually redeployed the same commit after the first
attempt. Do not treat a missing checkpoint as permission to resubmit.

**Future failure diagnosis:** FalProviderError now carries a limited,
constant/HTTP-numeric error category (http_401/http_403/http_422,
timeout_ambiguous, transport_ambiguous, invalid_json) without exposing key,
prompt, response body or sensitive URL. The admin-only bot displays the category
only when a separately approved future attempt fails. No retrospective
original category can be inferred.

**Release policy:** This PR is code/tests only; do NOT merge/deploy until
account usage is reviewed and rollout is explicitly approved. Production
customer checkout, wallet, receipts, model mapping and FAL_KEY values
are untouched. New code does not make any paid request automatically.
