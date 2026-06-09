"""Post intents to EDA webhook."""
from __future__ import annotations

import logging

import httpx

from .models import Intent

log = logging.getLogger(__name__)


def post_to_eda(intent: Intent, url: str, token: str) -> None:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = httpx.post(url, json=intent.model_dump(), headers=headers)
    except httpx.ConnectError:
        log.warning("EDA not reachable at %s — skipping POST", url)
        return
    resp.raise_for_status()
