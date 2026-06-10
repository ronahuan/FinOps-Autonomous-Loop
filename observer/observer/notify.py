"""Post intents to EDA webhook."""
from __future__ import annotations

import logging

import httpx

from .models import Intent

log = logging.getLogger(__name__)


def post_to_eda(intent: Intent, url: str, username: str = "", password: str = "") -> None:
    auth = (username, password) if username else None
    try:
        resp = httpx.post(url, json=intent.model_dump(), auth=auth)
    except httpx.ConnectError:
        log.warning("EDA not reachable at %s — skipping POST", url)
        return
    resp.raise_for_status()
