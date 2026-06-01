"""Resource parsing and savings estimation."""
from __future__ import annotations

import re

from .models import Recommendation, ResourceSet

_CPU_RE = re.compile(r"^(\d+(?:\.\d+)?)(m?)$")
_MEM_RE = re.compile(r"^(\d+(?:\.\d+)?)(Ki|Mi|Gi|K|M|G|)$")

_MEM_MULTIPLIERS: dict[str, int] = {
    "": 1,
    "K": 1_000,
    "M": 1_000_000,
    "G": 1_000_000_000,
    "Ki": 1024,
    "Mi": 1024 ** 2,
    "Gi": 1024 ** 3,
}


def parse_cpu(q: str) -> float:
    m = _CPU_RE.match(q)
    if not m:
        raise ValueError(f"cannot parse CPU quantity: {q!r}")
    value = float(m.group(1))
    if m.group(2) == "m":
        return value
    return value * 1000


def parse_mem(q: str) -> int:
    m = _MEM_RE.match(q)
    if not m:
        raise ValueError(f"cannot parse memory quantity: {q!r}")
    value = float(m.group(1))
    suffix = m.group(2)
    return int(value * _MEM_MULTIPLIERS[suffix])


def gap_pct(current: ResourceSet, recommended: ResourceSet) -> float:
    cpu_cur = parse_cpu(current.cpu_request)
    cpu_rec = parse_cpu(recommended.cpu_request)
    mem_cur = parse_mem(current.memory_request)
    mem_rec = parse_mem(recommended.memory_request)

    cpu_pct = ((cpu_cur - cpu_rec) / cpu_cur * 100) if cpu_cur else 0.0
    mem_pct = ((mem_cur - mem_rec) / mem_cur * 100) if mem_cur else 0.0

    return max(cpu_pct, mem_pct)


def estimate_monthly(rec: Recommendation, cpu_rate: float, mem_gib_rate: float) -> float:
    cpu_delta = (parse_cpu(rec.current.cpu_request) - parse_cpu(rec.recommended.cpu_request)) / 1000
    mem_delta = (parse_mem(rec.current.memory_request) - parse_mem(rec.recommended.memory_request)) / (1024 ** 3)
    return (cpu_delta * cpu_rate + mem_delta * mem_gib_rate) * 730
