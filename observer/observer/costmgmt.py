"""Cost Management adapter.

MVP: load recommendations from a local JSON fixture.
Live: pull recommendations from the Cost Management API.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import httpx

from .auth import ConsoleAuth
from .models import Recommendation, ResourceSet

RECOMMENDATIONS_URL = (
    "https://console.redhat.com/api/cost-management/v1/recommendations/openshift"
)


def _cpu_cores_to_k8s(amount: float) -> str:
    millicores = round(amount * 1000)
    if millicores >= 1000 and millicores % 1000 == 0:
        return str(millicores // 1000)
    return f"{millicores}m"


def _bytes_to_k8s_mem(amount: float) -> str:
    mib = amount / (1024 ** 2)
    if mib >= 1024 and mib % 1024 == 0:
        return f"{int(mib // 1024)}Gi"
    return f"{math.ceil(mib)}Mi"


def _parse_api_item(item: dict) -> Recommendation:
    recs = item["recommendations"]
    current_req = recs["current"]["requests"]
    terms = recs["recommendation_terms"]
    short = terms.get("short_term") or terms.get("medium_term") or terms.get("long_term")
    cost_cfg = short["recommendation_engines"]["cost"]["config"]["requests"]
    duration_hours = short.get("duration_in_hours", 0)

    if duration_hours >= 24:
        term_str = f"{int(duration_hours // 24)}d"
    else:
        term_str = f"{duration_hours}h"

    return Recommendation(
        cluster=item.get("cluster_alias", ""),
        namespace=item["project"],
        workload=item["workload"],
        workload_type=item["workload_type"].title(),
        container=item["container"],
        current=ResourceSet(
            cpu_request=_cpu_cores_to_k8s(current_req["cpu"]["amount"]),
            memory_request=_bytes_to_k8s_mem(current_req["memory"]["amount"]),
        ),
        recommended=ResourceSet(
            cpu_request=_cpu_cores_to_k8s(cost_cfg["cpu"]["amount"]),
            memory_request=_bytes_to_k8s_mem(cost_cfg["memory"]["amount"]),
        ),
        recommendation_term=term_str,
        last_reported=item["last_reported"],
    )


def recommendations(client_id: str, client_secret: str) -> list[Recommendation]:
    auth = ConsoleAuth(client_id, client_secret)
    token = auth.bearer()
    resp = httpx.get(
        RECOMMENDATIONS_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return [_parse_api_item(item) for item in data]


def _parse(raw: dict) -> Recommendation:
    return Recommendation.model_validate(raw)


def load_fixture(path: str | Path, refresh_dates: bool = True) -> list[Recommendation]:
    data = json.loads(Path(path).read_text())
    recs = [_parse(item) for item in data]
    if refresh_dates:
        from datetime import datetime, timezone, timedelta
        fresh = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for rec in recs:
            rec.last_reported = fresh
    return recs
