"""Tests for savings parsing and estimation."""
import pytest

from observer.models import Recommendation, ResourceSet
from observer.savings import parse_cpu, parse_mem, gap_pct, estimate_monthly


def _rec(cpu_cur="500m", mem_cur="512Mi", cpu_rec="50m", mem_rec="64Mi"):
    return Recommendation(
        cluster="crc",
        namespace="finops-demo",
        workload="waster",
        workload_type="Deployment",
        container="waster",
        current=ResourceSet(cpu_request=cpu_cur, memory_request=mem_cur),
        recommended=ResourceSet(cpu_request=cpu_rec, memory_request=mem_rec),
        recommendation_term="15d",
        last_reported="2026-06-01T00:00:00Z",
    )


class TestParseCpu:
    def test_millicores(self):
        assert parse_cpu("500m") == 500.0

    def test_whole_cores(self):
        assert parse_cpu("2") == 2000.0

    def test_fractional_cores(self):
        assert parse_cpu("0.5") == 500.0

    def test_one_millicore(self):
        assert parse_cpu("1m") == 1.0

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_cpu("abc")


class TestParseMem:
    def test_mi(self):
        assert parse_mem("512Mi") == 512 * 1024 ** 2

    def test_gi(self):
        assert parse_mem("1Gi") == 1024 ** 3

    def test_ki(self):
        assert parse_mem("1024Ki") == 1024 * 1024

    def test_decimal_si_M(self):
        assert parse_mem("100M") == 100_000_000

    def test_decimal_si_G(self):
        assert parse_mem("1G") == 1_000_000_000

    def test_decimal_si_K(self):
        assert parse_mem("500K") == 500_000

    def test_bare_bytes(self):
        assert parse_mem("1048576") == 1048576

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_mem("abc")


class TestGapPct:
    def test_fixture_values(self):
        rec = _rec()
        pct = gap_pct(rec.current, rec.recommended)
        assert pct == pytest.approx(90.0)

    def test_no_change(self):
        rec = _rec(cpu_rec="500m", mem_rec="512Mi")
        assert gap_pct(rec.current, rec.recommended) == pytest.approx(0.0)

    def test_returns_larger_reduction(self):
        rec = _rec(cpu_cur="100m", cpu_rec="50m", mem_cur="512Mi", mem_rec="64Mi")
        pct = gap_pct(rec.current, rec.recommended)
        assert pct == pytest.approx(87.5)


class TestEstimateMonthly:
    def test_fixture_values(self):
        rec = _rec()
        saving = estimate_monthly(rec, cpu_rate=0.03, mem_gib_rate=0.005)
        assert saving > 0

    def test_known_calculation(self):
        rec = _rec(cpu_cur="1", cpu_rec="500m", mem_cur="1Gi", mem_rec="512Mi")
        saving = estimate_monthly(rec, cpu_rate=0.03, mem_gib_rate=0.005)
        expected = (0.5 * 0.03 + 0.5 * 0.005) * 730
        assert saving == pytest.approx(expected)

    def test_no_change_zero_saving(self):
        rec = _rec(cpu_rec="500m", mem_rec="512Mi")
        assert estimate_monthly(rec, cpu_rate=0.03, mem_gib_rate=0.005) == pytest.approx(0.0)
