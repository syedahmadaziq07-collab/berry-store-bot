"""Server-side fal.ai queue client. No network calls on import.

Never expose FAL_KEY to Telegram messages, frontend bundles, or logs.
Billing and Telegram delivery are deliberately separate integrations.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import httpx

_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_./-]*$")
_REQUEST = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class FalProviderError(RuntimeError):
    pass


class FalProvider:
    def __init__(self, api_key=None, client=None):
        self._key = api_key if api_key is not None else os.environ.get("FAL_KEY", "")
        self._client = client or httpx.Client(timeout=30, follow_redirects=False)

    def configured(self):
        return bool(self._key and self._key.strip())

    def _headers(self):
        if not self.configured():
            raise FalProviderError("FAL_KEY is not configured")
        return {"Authorization": "Key " + self._key, "Content-Type": "application/json"}

    @staticmethod
    def _model(model_id):
        if not isinstance(model_id, str) or not _MODEL.fullmatch(model_id) or ".." in model_id:
            raise FalProviderError("Invalid fal.ai model identifier")
        return model_id

    @staticmethod
    def _url(url):
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname != "queue.fal.run" or
                parsed.username or parsed.password or parsed.port or parsed.query or
                parsed.fragment or not parsed.path.startswith("/")):
            raise FalProviderError("Untrusted fal.ai queue URL")
        return url

    def _request(self, method, url, **kwargs):
        try:
            response = self._client.request(method, self._url(url), headers=self._headers(), **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FalProviderError("fal.ai request failed") from exc

    def submit(self, model_id, arguments):
        if not isinstance(arguments, dict):
            raise FalProviderError("Model arguments must be an object")
        model_id = self._model(model_id)
        return self._request("POST", "https://queue.fal.run/" + model_id, json=arguments)

    def status(self, status_url):
        return self._request("GET", status_url)

    def result(self, response_url):
        return self._request("GET", response_url)
