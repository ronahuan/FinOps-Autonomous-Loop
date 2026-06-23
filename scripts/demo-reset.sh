#!/bin/bash
# Reset the environment for a clean demo
set -e

echo "=== Resetting waster workload ==="
oc apply -f actor/test-workload.yaml

echo "=== Clearing suppression annotation ==="
oc annotate deploy waster -n finops-demo finops.redhat.com/suppressed-until- 2>/dev/null || true
oc annotate deploy waster -n finops-demo finops.redhat.com/last-saving- 2>/dev/null || true
oc annotate deploy waster -n finops-demo finops.redhat.com/last-remediated- 2>/dev/null || true
oc annotate deploy waster -n finops-demo finops.redhat.com/patched-cpu- 2>/dev/null || true
oc annotate deploy waster -n finops-demo finops.redhat.com/patched-mem- 2>/dev/null || true

echo "=== Waiting for pod to be ready ==="
oc rollout status deploy/waster -n finops-demo --timeout=120s

echo "=== Current state ==="
echo "Requests:"
oc get deploy waster -n finops-demo -o jsonpath='  CPU: {.spec.template.spec.containers[0].resources.requests.cpu}  Memory: {.spec.template.spec.containers[0].resources.requests.memory}'
echo ""
echo ""
echo "=== Ready for demo ==="
