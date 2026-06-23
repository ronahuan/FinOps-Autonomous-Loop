#!/bin/bash
# Run the demo — shows the full loop
set -e

source .env
export K8S_OBSERVER_TOKEN=$(oc get secret finops-observer-token -n finops-demo -o jsonpath='{.data.token}' | base64 -d)
export K8S_AUTH_VERIFY_SSL=false

echo "=== Step 1: Current workload state ==="
echo "Requests:"
oc get deploy waster -n finops-demo -o jsonpath='  CPU: {.spec.template.spec.containers[0].resources.requests.cpu}  Memory: {.spec.template.spec.containers[0].resources.requests.memory}'
echo ""
echo ""

echo "=== Step 2: Running Observer (evaluating recommendation) ==="
USE_LIVE_API=false python -m observer.main

echo ""
echo "=== Step 3: Check Slack for notification ==="
echo "=== Step 4: Approve in AAP dashboard ==="
echo "=== Step 5: After approval, check new state: ==="
echo "  oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'"
echo "=== Step 6: Check savings annotation: ==="
echo "  oc get deploy waster -n finops-demo -o jsonpath='{.metadata.annotations.finops\.redhat\.com/last-saving}'"
