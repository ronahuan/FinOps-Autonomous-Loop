#!/usr/bin/env bash
# Runs the Observer and posts the proposal to EDA (triggers Slack).
# Run from the repo root: ./scripts/run-loop.sh
source scripts/env-observer.sh
unset KUBECONFIG
echo ""
python3 -m observer.main 2>/dev/null
