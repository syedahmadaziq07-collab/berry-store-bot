"""Owner-only, read-only fal.ai authentication probe. No model execution."""
import asyncio
import os
import httpx

PRICING_URL = "https://api.fal.ai/v1/models/pricing"
MODEL = "minimax/h3-max-turbo/text-to-video"


def check_fal_pricing_auth(*, api_key=None, client=None):
    """Return safe status, never provider body, headers, key or URL."""
    key = os.environ.get("FAL_KEY", "") if api_key is None else api_key
    if not isinstance(key, str) or not key.strip():
        return "missing_key"
    key = key.strip()
    if any(ch.isspace() or ord(ch) < 33 or ord(ch) == 127 for ch in key):
        return "invalid_key_format"
    try:
        if client is None:
            with httpx.Client(timeout=15, follow_redirects=False) as owned:
                response = owned.get(PRICING_URL, params={"endpoint_id": MODEL},
                                     headers={"Authorization": "Key " + key})
        else:
            response = client.get(PRICING_URL, params={"endpoint_id": MODEL},
                                  headers={"Authorization": "Key " + key})
        status = response.status_code
        if status == 200:
            return "http_200"
        return "http_" + str(status) if 100 <= status <= 599 else "http_unexpected"
    except httpx.TimeoutException:
        return "timeout"
    except httpx.RequestError:
        return "transport_error"


async def owner_fal_auth(update, context):
    user = getattr(update, "effective_user", None)
    chat = getattr(update, "effective_chat", None)
    admin_id = int(os.environ.get("ADMIN_ID", "0") or "0")
    if not admin_id or user is None or chat is None:
        return
    if user.id != admin_id or chat.id != admin_id or chat.type != "private":
        return
    result = await asyncio.to_thread(check_fal_pricing_auth)
    await update.message.reply_text(
        "fal.ai read-only pricing auth: " + result +
        "\\nNo model submitted. HTTP 200 confirms read-only pricing access only; "
        "it does not guarantee queue submit permission."
    )
