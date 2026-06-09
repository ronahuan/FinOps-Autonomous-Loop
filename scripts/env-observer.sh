#!/usr/bin/env bash
# Source this file from the repo root: source scripts/env-observer.sh
set -a; source .env; set +a
export KUBECONFIG=~/.crc/machines/crc/kubeconfig
export K8S_AUTH_HOST=https://api.crc.testing:6443
export K8S_AUTH_VERIFY_SSL=false
export K8S_OBSERVER_TOKEN=$(oc get secret finops-observer-token -n finops-demo -o jsonpath='{.data.token}' | base64 -d)
echo "Observer env loaded (K8S_OBSERVER_TOKEN=${#K8S_OBSERVER_TOKEN} chars)"
