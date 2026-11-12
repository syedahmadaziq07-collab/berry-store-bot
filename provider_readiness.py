"""Read-only provider pricing probe, restricted to the isolated staging service.

No inference, purchases, key output, response-body output or HTTP redirects.
Pricing access is NOT model authorization, balance verification or a cost ceiling.
"""
import json
import os
import re
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

def minimum_video_sale_cents(unit_usd_per_second, max_billable_seconds,
                             fx_myr_per_usd_bound, fixed_myr_bound, sale_fee_fraction):
    """Require a separately verified maximum billed duration, not requested duration.

    Caller must verify rate applicability, maximum billable seconds, FX and fees.
    Authenticated unit-price metadata alone never certifies this calculation.
    """
    try:
        unit = Decimal(str(unit_usd_per_second))
        seconds = Decimal(str(max_billable_seconds))
        if not unit.is_finite() or not seconds.is_finite() or unit <= 0 or seconds <= 0:
            raise ValueError()
        return minimum_sale_cents(unit * seconds, fx_myr_per_usd_bound,
                                  fixed_myr_bound, sale_fee_fraction)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ValueError('Verified finite cost bounds required') from None


class PricingContractError(ValueError):
    """Constant diagnostic codes only; never include provider data or exceptions."""


def parse_pricing(payload, model):
    """Validate the published pricing envelope before reading a bounded price row.

    A pricing read is not a maximum inference cost or model-access proof.
    Unrecognized billing units remain blocked rather than guessed.
    """
    if not isinstance(payload, dict):
        raise PricingContractError('envelope_not_object')
    if 'prices' not in payload:
        raise PricingContractError('prices_missing')
    rows = payload['prices']
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise PricingContractError('prices_not_object_array')
    matches = [row for row in rows if row.get('endpoint_id') == model]
    if not matches:
        raise PricingContractError('endpoint_not_found')
    if len(matches) != 1:
        raise PricingContractError('endpoint_ambiguous')
    row = matches[0]
    value = row.get('unit_price')
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise PricingContractError('price_type_invalid')
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        raise PricingContractError('price_value_invalid') from None
    if not price.is_finite() or price < 0 or price > 100000:
        raise PricingContractError('price_value_invalid')
    if row.get('currency') != 'USD':
        raise PricingContractError('currency_unsupported')
    if row.get('unit') not in ('image', 'images', 'megapixel', 'megapixels', 'second', 'seconds', 'video', 'videos', 'request', 'requests', 'video_second'):
        raise PricingContractError('billing_unit_unsupported')
    return {'status': 'pricing_read_verified', 'unit_price': str(price),
            'unit': row['unit'], 'currency': 'USD'}

def pricing_probe(key,client):
    # Environment secrets can acquire a trailing newline on secure paste. Normalize only
    # outer whitespace; embedded whitespace/control characters must fail before HTTP.
    key=key.strip() if isinstance(key,str) else ''
    if not re.fullmatch(r'[!-~]{1,4096}',key):
        return [{'model':m,'status':'unverified','error_kind':'credential_format_invalid'} for m in MODELS]
    results=[]
    for model in MODELS:
        item={'model':model,'status':'unverified'}
        try:
            response=client.get('https://api.fal.ai/v1/models/pricing',params={'endpoint_id':model},
                headers={'Authorization':'Key '+key},follow_redirects=False,timeout=10)
            item['http_status']=response.status_code
            if response.status_code==200:
                try:
                    payload = response.json()
                except (ValueError, UnicodeError):
                    raise PricingContractError('body_not_json') from None
                item.update(parse_pricing(payload, model))
        except PricingContractError as exc:
            item['error_kind'] = 'invalid_response'
            item['validation_error'] = str(exc)  # Internal constant; never response content.
        except httpx.TimeoutException:
            item['error_kind']='timeout'
        except httpx.LocalProtocolError:
            item['error_kind']='local_request_rejected'
        except httpx.RequestError:
            item['error_kind']='transport_error'
        except (TypeError,AttributeError):
            item['error_kind']='client_or_response_contract'
        except Exception:
            item['error_kind']='invalid_response' # Never log provider response or exception text.
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
        emit('BERRY_PROVIDER_ACCOUNT_READONLY '+json.dumps(account_balance_probe(key,client),sort_keys=True),flush=True)


def account_balance_probe(key, client):
    """GET only; expose positive-balance boolean, never identity or raw billing data.

    Pricing permission does not imply billing permission or inference authorization.
    A positive balance is not sufficient-budget evidence until a cost cap is verified.
    """
    key = key.strip() if isinstance(key, str) else ''
    result = {'status': 'unverified', 'inference_access_verified': False}
    if not re.fullmatch(r'[!-~]{1,4096}', key):
        return dict(result, error_kind='credential_format_invalid')
    try:
        response = client.get('https://api.fal.ai/v1/account/billing', params={'expand': 'credits'},
                              headers={'Authorization': 'Key ' + key}, follow_redirects=False, timeout=10)
        result['http_status'] = response.status_code
        if response.status_code != 200:
            return result
        payload = response.json()
        credits = payload.get('credits') if isinstance(payload, dict) else None
        if not isinstance(credits, dict) or credits.get('currency') != 'USD':
            return dict(result, error_kind='invalid_response')
        value = credits.get('current_balance')
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return dict(result, error_kind='invalid_response')
        balance = Decimal(str(value))
        if not balance.is_finite() or balance < 0:
            return dict(result, error_kind='invalid_response')
        result.update(status='balance_read_verified', positive_balance=balance > 0)
    except httpx.RequestError:
        result['error_kind'] = 'transport_error'
    except Exception:
        result['error_kind'] = 'invalid_response'
    return result
