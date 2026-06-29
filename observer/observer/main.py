"""Observer main loop — load recommendations, decide, emit intents."""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

from .config import (
    STALE_DAYS, MIN_GAP_PCT, MIN_SAVING_USD, CPU_RATE, MEM_GIB_RATE,
    EDA_WEBHOOK_URL, EDA_WEBHOOK_USER, EDA_WEBHOOK_PASSWORD,
    USE_LIVE_API, RH_CLIENT_ID, RH_CLIENT_SECRET,
)
from .costmgmt import load_fixture, recommendations
from .cluster import Cluster
from .savings import gap_pct, estimate_monthly
from .gates import decide
from .models import Intent
from .notify import post_to_eda


def _is_suppressed(facts: dict) -> bool:
    annotations = facts.get("annotations", {})
    suppressed_until = annotations.get("finops.redhat.com/suppressed-until", "")
    if not suppressed_until:
        return False
    from datetime import datetime, timezone
    try:
        expiry = datetime.fromisoformat(suppressed_until.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) < expiry
    except ValueError:
        return False


def _load_clusters(config_path: Path) -> tuple[dict[str, Cluster], dict[str, str]]:
    if not config_path.exists():
        return {"_default": Cluster()}, {}

    data = json.loads(config_path.read_text())
    clusters = {}
    uuid_to_alias = {}
    for alias, cfg in data["clusters"].items():
        token = os.environ.get(cfg["token_env"], "")
        if not token:
            print(f"WARNING: {cfg['token_env']} not set — skipping cluster '{alias}'")
            continue
        clusters[alias] = Cluster(
            host=cfg["api_host"],
            token=token,
            verify_ssl=cfg.get("verify_ssl", True),
        )
        if "cluster_uuid" in cfg:
            uuid_to_alias[cfg["cluster_uuid"]] = alias
    return clusters, uuid_to_alias


def main() -> None:
    fixture_path = REPO_ROOT / "observer" / "tests" / "fixtures" / "recommendation.json"
    clusters_config = REPO_ROOT / "observer" / "clusters.json"
    proposals_dir = REPO_ROOT / "observer" / "out" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    if USE_LIVE_API:
        recs = recommendations(RH_CLIENT_ID, RH_CLIENT_SECRET)
    else:
        recs = load_fixture(fixture_path)

    clusters, uuid_to_alias = _load_clusters(clusters_config)

    cfg = {
        "stale_days": STALE_DAYS,
        "min_gap_pct": MIN_GAP_PCT,
        "min_saving_usd": MIN_SAVING_USD,
    }

    for rec in recs:
        alias = uuid_to_alias.get(rec.cluster, rec.cluster)
        cluster_obj = clusters.get(alias) or clusters.get(rec.cluster) or clusters.get("_default")
        if not cluster_obj:
            print(f"No cluster config for '{rec.cluster}' — skipping")
            continue
        rec.cluster = alias

        facts = cluster_obj.workload_facts(rec.namespace, rec.workload, rec.container)
        facts["suppressed"] = _is_suppressed(facts)

        gap = gap_pct(rec.current, rec.recommended)
        saving = estimate_monthly(rec, CPU_RATE, MEM_GIB_RATE)

        decision, reasons = decide(rec, facts, gap, saving, cfg)

        intent = Intent(
            **rec.model_dump(),
            stage="proposed",
            decision=decision,
            reasons=reasons,
            monthly_saving_estimate=saving,
        )

        filename = f"{rec.cluster}__{rec.namespace}__{rec.workload}.json"
        proposal_path = proposals_dir / filename
        proposal_path.write_text(json.dumps(intent.model_dump(), indent=2) + "\n")

        print(json.dumps(intent.model_dump(), indent=2))
        post_to_eda(intent, EDA_WEBHOOK_URL, EDA_WEBHOOK_USER, EDA_WEBHOOK_PASSWORD)

        if decision == "approve":
            print(f"\n  python approve.py observer/out/proposals/{filename}")


if __name__ == "__main__":
    main()
