"""Quick-check: load fixture, gather facts, run decide(), print result."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

from observer.config import STALE_DAYS, MIN_GAP_PCT, MIN_SAVING_USD, CPU_RATE, MEM_GIB_RATE
from observer.costmgmt import load_fixture
from observer.cluster import Cluster
from observer.savings import gap_pct, estimate_monthly
from observer.gates import decide
from observer.main import _is_suppressed


def main() -> None:
    fixture_path = REPO_ROOT / "observer" / "tests" / "fixtures" / "recommendation.json"

    recs = load_fixture(fixture_path)
    cluster = Cluster()

    cfg = {
        "stale_days": STALE_DAYS,
        "min_gap_pct": MIN_GAP_PCT,
        "min_saving_usd": MIN_SAVING_USD,
    }

    for rec in recs:
        facts = cluster.workload_facts(rec.namespace, rec.workload, rec.container)
        facts["suppressed"] = _is_suppressed(facts)

        gap = gap_pct(rec.current, rec.recommended)
        saving = estimate_monthly(rec, CPU_RATE, MEM_GIB_RATE)

        decision, reasons = decide(rec, facts, gap, saving, cfg)
        print((decision, reasons))


if __name__ == "__main__":
    main()
