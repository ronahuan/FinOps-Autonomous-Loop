"""Observer main loop — load recommendations, decide, emit intents."""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

from .config import (
    STALE_DAYS, MIN_GAP_PCT, MIN_SAVING_USD, CPU_RATE, MEM_GIB_RATE,
    EDA_WEBHOOK_URL, EDA_WEBHOOK_TOKEN,
)
from .costmgmt import load_fixture
from .cluster import Cluster
from .savings import gap_pct, estimate_monthly
from .gates import decide
from .models import Intent
from .notify import post_to_eda


def main() -> None:
    fixture_path = REPO_ROOT / "observer" / "tests" / "fixtures" / "recommendation.json"
    suppress_path = REPO_ROOT / "actor" / "out" / "suppress.txt"
    proposals_dir = REPO_ROOT / "observer" / "out" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    recs = load_fixture(fixture_path)
    cluster = Cluster()

    cfg = {
        "stale_days": STALE_DAYS,
        "min_gap_pct": MIN_GAP_PCT,
        "min_saving_usd": MIN_SAVING_USD,
    }

    for rec in recs:
        facts = cluster.workload_facts(rec.namespace, rec.workload, rec.container)

        suppressed = False
        if suppress_path.exists():
            suppressed_workloads = suppress_path.read_text().strip().splitlines()
            suppressed = f"{rec.namespace}/{rec.workload}" in suppressed_workloads
        facts["suppressed"] = suppressed

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

        filename = f"{rec.namespace}__{rec.workload}.json"
        proposal_path = proposals_dir / filename
        proposal_path.write_text(json.dumps(intent.model_dump(), indent=2) + "\n")

        print(json.dumps(intent.model_dump(), indent=2))
        post_to_eda(intent, EDA_WEBHOOK_URL, EDA_WEBHOOK_TOKEN)

        if decision == "approve":
            print(f"\n  python approve.py observer/out/proposals/{filename}")


if __name__ == "__main__":
    main()
