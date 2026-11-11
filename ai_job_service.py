"""Fail-closed AI job preparation for an isolated Telegram staging worker.

This module NEVER charges customers or submits generation by itself.
A durable, idempotent wallet reservation must be implemented before calling submit.
"""
from __future__ import annotations

from dataclasses import dataclass
from ai_model_mapping_store import PrivateMappingStore, PrivateMappingError
from fal_provider import FalProvider, FalProviderError


class AIJobNotReady(RuntimeError):
    pass


@dataclass(frozen=True)
class AIJobQuote:
    tool_key: str
    display_name: str
    provider_model_id: str
    credits: int
    mapping_revision: int


class AIJobService:
    def __init__(self, mapping_store: PrivateMappingStore, provider: FalProvider):
        self.mapping_store = mapping_store
        self.provider = provider

    def quote(self, tool_key: str) -> AIJobQuote:
        if tool_key not in ("image", "video"):
            raise AIJobNotReady("Tool not supported for generation")
        if not self.mapping_store.configured() or not self.provider.configured():
            raise AIJobNotReady("AI provider or private mapping not configured")
        payload = self.mapping_store.get()
        for row in payload["mappings"]:
            if row["tool_key"] == tool_key and row["enabled"]:
                model = row["provider_model_id"]
                # Never route test placeholders or zero-priced jobs to a billable provider.
                if model.startswith("test/") or row["credit_cost"] <= 0:
                    raise AIJobNotReady("Real model and positive credit price required")
                self.provider._model(model)
                return AIJobQuote(tool_key, row["display_name"], model,
                                  row["credit_cost"], payload["revision"])
        raise AIJobNotReady("No enabled model for tool")

    def submit_reserved(self, quote: AIJobQuote, arguments: dict, *, reservation_id: str,
                        verify_reservation):
        """Submit only after a trusted durable wallet verifies a matching reservation.

        verify_reservation must validate the customer, job id, quoted credits,
        revision and exactly-once reservation state. Never pass a client-supplied
        callback in an HTTP handler. A timeout yields UNKNOWN, not an automatic
        second provider submission or a blind refund.
        """
        # A boolean callback cannot atomically consume the right to submit.
        # Repeated calls with the same reservation could otherwise bill twice.
        # Use StagingJobWorker's durable claim for isolated staging tests instead.
        raise AIJobNotReady("Legacy callback submission disabled; durable atomic claim required")
