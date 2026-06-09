#!/usr/bin/env bash
# One-time setup: resets the workload, starts EDA, and waits for it to be ready.
# Run from the repo root: ./scripts/setup-demo.sh
# Leave this terminal running — EDA stays in the foreground.

source scripts/reset.sh
echo ""

source scripts/env-actor.sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export FINOPS_ACTOR_OUT="$(pwd)/actor/out"
unset KUBECONFIG

echo ""
echo "Starting EDA — leave this terminal running."
echo "Use another terminal for the demo."
echo ""
ansible-rulebook --rulebook eda/rulebooks/loop.yml -i actor/inventory/hosts.yml \
  --env-vars EDA_WEBHOOK_TOKEN,SLACK_WEBHOOK_URL --verbose
