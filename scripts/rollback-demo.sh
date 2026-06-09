#!/usr/bin/env bash
# Demonstrates auto-rollback by applying a bad recommendation (requests exceed limits).
# Run from the repo root: ./scripts/rollback-demo.sh
source scripts/env-actor.sh
unset KUBECONFIG
echo ""
echo "Applying a bad recommendation — 800m CPU request exceeds the 500m limit..."
echo ""
ansible-playbook actor/playbooks/remediate-safe.yml -i actor/inventory/hosts.yml \
  -e namespace=finops-demo -e workload=waster -e container=waster \
  -e cpu_req=800m -e mem_req=64Mi
