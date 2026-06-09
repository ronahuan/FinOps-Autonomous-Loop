"""Human approval gate — promote a proposed intent to approved and POST to EDA."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "observer"))
from observer.models import Intent


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <proposal.json>")
        sys.exit(1)

    path = sys.argv[1]
    data = json.loads(open(path).read())
    intent = Intent(**data)

    if intent.stage != "proposed":
        print(f"Refused: stage is '{intent.stage}', expected 'proposed'.")
        sys.exit(1)
    if intent.decision != "approve":
        print(f"Refused: decision is '{intent.decision}', cannot approve a blocked intent.")
        sys.exit(1)

    intent.stage = "approved"
    Intent.model_validate(intent.model_dump())

    url = os.environ.get("EDA_WEBHOOK_URL", "http://127.0.0.1:5000/endpoint")
    token = os.environ.get("EDA_WEBHOOK_TOKEN", "")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.post(url, json=intent.model_dump(), headers=headers)
    resp.raise_for_status()
    print(f"Approved and posted to EDA: {resp.status_code}")


if __name__ == "__main__":
    main()
