#!/usr/bin/env bash
# Approve the proposal and send to EDA for remediation.
# Run from the repo root: ./scripts/approve.sh
source scripts/env-actor.sh
echo ""
python3 approve.py observer/out/proposals/finops-demo__waster.json
