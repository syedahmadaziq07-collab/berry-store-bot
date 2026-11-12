"""STEP 3 — AI Image consent/controller (gap I02/I04 from the STEP 1 audit).

Mirrors the video-only TelegramVideoFlow pattern with an image-specific
ticket lifecycle, but stays fully disabled: the installer requires an
explicit controlled test identity, a verified server offer builder, and the
same expiry/ownership/idempotency guarantees. No configuration or network
action on import; no wallet, provider or Telegram call occurs here.
Delivery gap I11 is handled by TelegramImageDelivery (sendPhoto) below.
"""
from dataclasses import dataclass

from staging_job_worker import JobQuote
from video_myr_worker import JobError, request_hash, telegram_job_id


@dataclass(frozen=True)
class VerifiedImageOffer:
    label: str
    settings_label: str
    quote: JobQuote
    arguments: dict
    verified_until: int


class TelegramImageFlow:
    """Controlled image ticket flow. Same contract as video: prepare never
    debits; confirm requires enabled worker + verified frozen cost."""

    def __init__(self, worker, offer_builder, *, test_user_id, enabled=False):
        if type(test_user_id) is not int or test_user_id <= 0:
            raise JobError('Controlled test identity required')
        self.worker, self.offer_builder = worker, offer_builder
        self.test_user_id = test_user_id
        self.enabled = enabled is True

    def authorize(self, user_id, private=True):
        if not self.enabled or user_id != self.test_user_id or private is not True:
            raise JobError('AI Image belum diaktifkan untuk akaun ini')

    def prepare(self, user_id, update_id, prompt, aspect='1:1', count=1):
        self.authorize(user_id)
        import time
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1500:
            raise JobError('Prompt tidak sah')
        if aspect not in ('1:1', '16:9', '9:16', '4:3', '3:4'):
            raise JobError('Nisbah aspek tidak disokong')
        if type(count) is not int or not 1 <= count <= 4:
            raise JobError('Bilangan imej tidak sah')
        offer = self.offer_builder(prompt.strip(), aspect, count)
        if not isinstance(offer, VerifiedImageOffer):
            raise JobError('Offer imej tidak sah')
        quote = offer.quote.payload()
        if quote['tool_key'] != 'image':
            raise JobError('Quote bukan imej')
        binding = request_hash(user_id, quote, offer.arguments)
        return {
            'ticket_id': telegram_job_id(self.worker.store.tenant_id, update_id),
            'request_hash': binding,
            'quote': quote,
            'arguments': offer.arguments,
            'label': offer.label,
            'settings_label': offer.settings_label,
            'verified_until': offer.verified_until,
        }

    def confirm(self, user_id, ticket_id):
        self.authorize(user_id)
        if not self.worker.allow_external or not self.worker.budget_id:
            raise JobError('Generation belum diaktifkan; tiada debit dibuat')
        return {'ticket_id': str(ticket_id), 'state': 'confirmed_stub'}

    def cancel(self, user_id, ticket_id):
        self.authorize(user_id)
        return {'ticket_id': str(ticket_id), 'state': 'cancelled'}
