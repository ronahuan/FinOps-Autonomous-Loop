"""Decision gates — pure functions that decide approve/block."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from .models import Recommendation


def is_fresh(rec: Recommendation, now: datetime, stale_days: int) -> tuple[bool, str]:
    if rec.recommendation_term == "24h":
        return False, "term is 24h (too short)"
    reported = datetime.fromisoformat(rec.last_reported).replace(tzinfo=timezone.utc)
    if now - reported > timedelta(days=stale_days):
        return False, f"last_reported is older than {stale_days} days"
    return True, "fresh"


def live_config_matches(rec: Recommendation, facts: dict) -> tuple[bool, str]:
    if facts["live_cpu_request"] != rec.current.cpu_request:
        return False, f"live cpu {facts['live_cpu_request']} != recommended baseline {rec.current.cpu_request}"
    if facts["live_mem_request"] != rec.current.memory_request:
        return False, f"live mem {facts['live_mem_request']} != recommended baseline {rec.current.memory_request}"
    return True, "live config matches"


def is_eligible(rec: Recommendation, facts: dict) -> tuple[bool, str]:
    if rec.workload_type != "Deployment":
        return False, f"workload_type {rec.workload_type} is not Deployment"
    if not facts.get("exists"):
        return False, "workload does not exist"
    if not facts.get("owner_label"):
        return False, "no owner label"
    if not facts.get("has_readiness_probe"):
        return False, "no readiness probe"
    if facts.get("recent_oom_or_crash"):
        return False, "recent OOM or crash"
    if facts.get("suppressed"):
        return False, "workload is suppressed"
    return True, "eligible"


def is_material(
    rec: Recommendation, gap: float, saving: float,
    min_gap_pct: float, min_saving_usd: float,
) -> tuple[bool, str]:
    if gap < min_gap_pct:
        return False, f"gap {gap:.1f}% < {min_gap_pct}%"
    if saving < min_saving_usd:
        return False, f"saving ${saving:.2f} < ${min_saving_usd}"
    return True, "material"


def decide(
    rec: Recommendation, facts: dict, gap: float, saving: float, cfg: dict,
    now: datetime | None = None,
) -> tuple[str, list[str]]:
    if now is None:
        now = datetime.now(timezone.utc)

    ok, reason = is_fresh(rec, now, cfg["stale_days"])
    if not ok:
        return "block", [reason]

    ok, reason = live_config_matches(rec, facts)
    if not ok:
        return "block", [reason]

    ok, reason = is_eligible(rec, facts)
    if not ok:
        return "block", [reason]

    ok, reason = is_material(rec, gap, saving, cfg["min_gap_pct"], cfg["min_saving_usd"])
    if not ok:
        return "block", [reason]

    return "approve", ["eligible", "fresh", "material"]
