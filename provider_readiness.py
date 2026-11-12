"""Read-only provider pricing probe, restricted to the isolated staging service.

No inference, purchases, key output, response-body output or HTTP redirects.
Pricing access is NOT model authorization, balance verification or a cost ceiling.
"""
import json
import os
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import httpx

MODELS=('fal-ai/flux/schnell','fal-ai/wan/v2.2-a14b/text-to-video','minimax/h3-max-turbo/text-to-video')
STAGING_SERVICE='srv-dbq2g9mk1f9s73de0u50'
STAGING_DATABASE='https://cirsdvkfkvypprnmyykk.supabase.co'

def minimum_sale_cents(provider_usd_bound, fx_myr_per_usd_bound, fixed_myr_bound, sale_fee_fraction):
    """Inputs must be independently verified upper bounds, never live quotes/estimates.
    Round UP to even cents: existing integer-credit ledger supports 25 credits/RM.02.
    fixed costs include taxes, FX fees, hosting, storage and delivery allocations.
    Fraction covers percentage fees applied to sale revenue. No automatic retries.
    """
    try:
        usd,fx,fixed,fee=map(lambda x:Decimal(str(x)),(provider_usd_bound,fx_myr_per_usd_bound,fixed_myr_bound,sale_fee_fraction))
        if not all(x.is_finite() for x in (usd,fx,fixed,fee)) or usd<=0 or fx<=0 or fixed<0 or not 0<=fee<1:
            raise ValueError()
        return int((((usd*fx+fixed+Decimal(1))/(1-fee))*50).to_integral_value(rounding=ROUND_CEILING))*2
    except (InvalidOperation,ValueError,TypeError,OverflowError):
        raise ValueError('Verified finite cost bounds required') from None

def pricing_probe(key,client):
    results=[]
    for model in MODELS:
        item={'model':model,'status':'unverified'}
        try:
            response=client.get('https://api.fal.ai/v1/models/pricing',params={'endpoint_id':model},
                headers={'Authorization':'Key '+key},follow_redirects=False,timeout=10)
            item['http_status']=response.status_code
            if response.status_code==200:
                rows=response.json().get('prices',[])
                rows=[r for r in rows if r.get('endpoint_id')==model]
                if len(rows)!=1:raise ValueError()
                row=rows[0];price=Decimal(str(row['unit_price']))
                if not price.is_finite() or price<0 or price>100000 or row.get('currency')!='USD' or row.get('unit') not in ('image','megapixel','second','video','request','video_second'):
                    raise ValueError()
                item.update(status='pricing_read_verified',unit_price=str(price),unit=row['unit'],currency='USD')
        except Exception:
            item['status']='unverified' # Never log provider response or exception text.
        results.append(item)
    return results

def staging_startup_probe(environ=None,client_factory=httpx.Client,emit=print):
    env=os.environ if environ is None else environ
    service_match=env.get('RENDER_SERVICE_ID')==STAGING_SERVICE
    database_match=env.get('SUPABASE_URL','').rstrip('/')==STAGING_DATABASE
    mapping_match=env.get('AI_MAPPING_SUPABASE_URL','').rstrip('/')==STAGING_DATABASE
    emit('BERRY_PROVIDER_READONLY_GATE '+json.dumps({'service_match':service_match,'database_match':database_match,'mapping_match':mapping_match}),flush=True)
    # Pricing GET never accesses any database. The isolated AI mapping config is its scope.
    # This does NOT relax business-wallet, controller or generation isolation checks.
    if not service_match or not (database_match or mapping_match):
        return
    key=env.get('FAL_KEY','') # Used internally for authentication only; never returned/logged.
    if not key:
        emit('BERRY_PROVIDER_READONLY '+json.dumps({'status':'credential_unavailable'}),flush=True);return
    with client_factory() as client:
        for result in pricing_probe(key,client):
            emit('BERRY_PROVIDER_READONLY '+json.dumps(result,sort_keys=True),flush=True)
