"""Red Hat SSO authentication (client_credentials)."""
from __future__ import annotations

import time

import httpx

SSO_TOKEN_URL = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"


class ConsoleAuth:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0

    def bearer(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        resp = httpx.post(
            SSO_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 300) - 30
        return self._token
