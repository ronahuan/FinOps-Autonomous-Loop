#!/usr/bin/env bash
# Run the Observer. Posts the proposed intent to EDA and triggers Slack.
# Run from the repo root: ./scripts/run-observer.sh
source scripts/env-observer.sh
unset KUBECONFIG
echo ""
python3 -m observer.main 2>/dev/null
