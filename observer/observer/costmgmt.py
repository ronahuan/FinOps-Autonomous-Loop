"""Cost Management adapter.

MVP: load recommendations from a local JSON fixture.
The live Cost Management API adapter is intentionally unbuilt.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import Recommendation


def _parse(raw: dict) -> Recommendation:
    return Recommendation.model_validate(raw)


def load_fixture(path: str | Path) -> list[Recommendation]:
    data = json.loads(Path(path).read_text())
    return [_parse(item) for item in data]
