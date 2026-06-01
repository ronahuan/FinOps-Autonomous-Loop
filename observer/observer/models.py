"""Data models for the FinOps Autonomous Loop.

`Intent` is the single contract object passed Observer -> EDA -> Actor.
Field names are fixed by contracts/remediation-intent.schema.json.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResourceSet(BaseModel):
    cpu_request: str
    memory_request: str


class Recommendation(BaseModel):
    cluster: str
    namespace: str
    workload: str
    workload_type: str
    container: str
    current: ResourceSet
    recommended: ResourceSet
    recommendation_term: str
    last_reported: str


class Intent(Recommendation):
    stage: Literal["proposed", "approved"] = "proposed"
    monthly_saving_estimate: float = 0.0
    decision: Literal["approve", "block"] = "block"
    reasons: list[str] = Field(default_factory=list)
