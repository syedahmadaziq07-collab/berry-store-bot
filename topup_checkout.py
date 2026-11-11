"""Atomic checkout client. No import-time I/O and no automatic write retries."""
from urllib.parse import urlparse
from uuid import UUID, uuid4, uuid5

import httpx


class CheckoutUnavailable(RuntimeError):
    pass


def create_topup_order(client, url, service_key, tenant_id, user_id, username, plan, update_id):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co")
            or parsed.username or parsed.password or parsed.port or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or not service_key):
        raise CheckoutUnavailable("Server checkout connection unavailable")
    tenant = str(UUID(tenant_id))
    if (type(user_id) is not int or user_id<=0 or type(update_id) is not int or update_id<0
            or plan not in ("starter","creator","pro","studio")
            or not isinstance(username,str) or len(username)>200):
        raise CheckoutUnavailable("Invalid checkout request")
    key = str(uuid5(UUID(tenant), f"berry-topup:{user_id}:{update_id}"))
    try:
        response = client.post(url.rstrip("/")+"/rest/v1/rpc/berry_create_topup_order",
            headers={"apikey":service_key,"Authorization":"Bearer "+service_key},
            json={"p_tenant":tenant,"p_user":user_id,"p_plan":plan,"p_key":key,
                  "p_proposed_id":"BT"+uuid4().hex[:24].upper(),"p_username":username},
            timeout=20,follow_redirects=False)
        response.raise_for_status()
        result = response.json()
        order = result["order"]
        if (not isinstance(order,dict) or order.get("tenant_id")!=tenant or order.get("user_id")!=user_id
                or not isinstance(order.get("id"),str) or not isinstance(order.get("status"),str)
                or type(result.get("created")) is not bool):
            raise ValueError()
        return order,result["created"]
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        raise CheckoutUnavailable("Checkout outcome unavailable; check active order before trying again") from None
