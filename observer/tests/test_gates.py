"""Tests for decision gates."""
from datetime import datetime, timezone, timedelta

import pytest

from observer.models import Recommendation, ResourceSet
from observer.gates import is_fresh, live_config_matches, is_eligible, is_material, decide

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(hours=6)).isoformat()
STALE = (NOW - timedelta(days=5)).isoformat()

CFG = {"stale_days": 2, "min_gap_pct": 20, "min_saving_usd": 5}


def _rec(last_reported=RECENT, term="15d", cpu_cur="500m", mem_cur="512Mi"):
    return Recommendation(
        cluster="crc",
        namespace="finops-demo",
        workload="waster",
        workload_type="Deployment",
        container="waster",
        current=ResourceSet(cpu_request=cpu_cur, memory_request=mem_cur),
        recommended=ResourceSet(cpu_request="50m", memory_request="64Mi"),
        recommendation_term=term,
        last_reported=last_reported,
    )


def _healthy_facts():
    return {
        "exists": True,
        "owner_label": "finops-intern",
        "has_readiness_probe": True,
        "recent_oom_or_crash": False,
        "suppressed": False,
        "live_cpu_request": "500m",
        "live_mem_request": "512Mi",
    }


class TestIsFresh:
    def test_fresh(self):
        ok, _ = is_fresh(_rec(), NOW, 2)
        assert ok

    def test_stale(self):
        ok, reason = is_fresh(_rec(last_reported=STALE), NOW, 2)
        assert not ok
        assert "older" in reason

    def test_24h_term(self):
        ok, reason = is_fresh(_rec(term="24h"), NOW, 2)
        assert not ok
        assert "24h" in reason


class TestLiveConfigMatches:
    def test_matches(self):
        ok, _ = live_config_matches(_rec(), _healthy_facts())
        assert ok

    def test_cpu_mismatch(self):
        facts = _healthy_facts()
        facts["live_cpu_request"] = "250m"
        ok, reason = live_config_matches(_rec(), facts)
        assert not ok
        assert "cpu" in reason

    def test_mem_mismatch(self):
        facts = _healthy_facts()
        facts["live_mem_request"] = "256Mi"
        ok, reason = live_config_matches(_rec(), facts)
        assert not ok
        assert "mem" in reason


class TestIsEligible:
    def test_eligible(self):
        ok, _ = is_eligible(_rec(), _healthy_facts())
        assert ok

    def test_not_deployment(self):
        rec = _rec()
        rec = rec.model_copy(update={"workload_type": "StatefulSet"})
        ok, reason = is_eligible(rec, _healthy_facts())
        assert not ok
        assert "Deployment" in reason

    def test_not_exists(self):
        facts = _healthy_facts()
        facts["exists"] = False
        ok, reason = is_eligible(_rec(), facts)
        assert not ok
        assert "not exist" in reason

    def test_no_owner(self):
        facts = _healthy_facts()
        facts["owner_label"] = ""
        ok, reason = is_eligible(_rec(), facts)
        assert not ok
        assert "owner" in reason

    def test_no_readiness_probe(self):
        facts = _healthy_facts()
        facts["has_readiness_probe"] = False
        ok, reason = is_eligible(_rec(), facts)
        assert not ok
        assert "readiness" in reason

    def test_recent_oom(self):
        facts = _healthy_facts()
        facts["recent_oom_or_crash"] = True
        ok, reason = is_eligible(_rec(), facts)
        assert not ok
        assert "OOM" in reason

    def test_suppressed(self):
        facts = _healthy_facts()
        facts["suppressed"] = True
        ok, reason = is_eligible(_rec(), facts)
        assert not ok
        assert "suppressed" in reason


class TestIsMaterial:
    def test_material(self):
        ok, _ = is_material(_rec(), 90.0, 11.0, 20, 5)
        assert ok

    def test_gap_too_small(self):
        ok, reason = is_material(_rec(), 10.0, 11.0, 20, 5)
        assert not ok
        assert "gap" in reason

    def test_saving_too_small(self):
        ok, reason = is_material(_rec(), 90.0, 2.0, 20, 5)
        assert not ok
        assert "saving" in reason


class TestDecide:
    def test_healthy_approve(self):
        decision, reasons = decide(_rec(), _healthy_facts(), 90.0, 11.0, CFG)
        assert decision == "approve"
        assert "eligible" in reasons
        assert "fresh" in reasons
        assert "material" in reasons

    def test_block_stale(self):
        decision, reasons = decide(_rec(last_reported=STALE), _healthy_facts(), 90.0, 11.0, CFG)
        assert decision == "block"
        assert "older" in reasons[0]

    def test_block_24h_term(self):
        decision, reasons = decide(_rec(term="24h"), _healthy_facts(), 90.0, 11.0, CFG)
        assert decision == "block"
        assert "24h" in reasons[0]

    def test_block_live_config_mismatch(self):
        facts = _healthy_facts()
        facts["live_cpu_request"] = "250m"
        decision, reasons = decide(_rec(), facts, 90.0, 11.0, CFG)
        assert decision == "block"
        assert "cpu" in reasons[0]

    def test_block_not_eligible(self):
        facts = _healthy_facts()
        facts["exists"] = False
        decision, reasons = decide(_rec(), facts, 90.0, 11.0, CFG)
        assert decision == "block"
        assert "not exist" in reasons[0]

    def test_block_not_material(self):
        decision, reasons = decide(_rec(), _healthy_facts(), 5.0, 1.0, CFG)
        assert decision == "block"
        assert "gap" in reasons[0]
