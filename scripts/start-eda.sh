#!/usr/bin/env bash
# Start the EDA rulebook in the foreground with all required env vars.
# Run from the repo root: ./scripts/start-eda.sh
source scripts/env-actor.sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export FINOPS_ACTOR_OUT="$(pwd)/actor/out"
unset KUBECONFIG
echo ""
echo "Starting EDA on 127.0.0.1:5000 ..."
echo "Leave this terminal running. Use another terminal for the demo."
echo ""
ansible-rulebook --rulebook eda/rulebooks/loop.yml -i actor/inventory/hosts.yml \
  --env-vars EDA_WEBHOOK_TOKEN,SLACK_WEBHOOK_URL --verbose
