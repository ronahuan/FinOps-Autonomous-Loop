#!/usr/bin/env bash
# Source this file from the repo root: source scripts/env-actor.sh
set -a; source .env; set +a
export KUBECONFIG=~/.crc/machines/crc/kubeconfig
export K8S_AUTH_HOST=https://api.crc.testing:6443
export K8S_AUTH_VERIFY_SSL=false
export K8S_AUTH_API_KEY=$(oc get secret finops-actor-token -n finops-demo -o jsonpath='{.data.token}' | base64 -d)
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export FINOPS_ACTOR_OUT="$(pwd)/actor/out"
echo "Actor env loaded (K8S_AUTH_API_KEY=${#K8S_AUTH_API_KEY} chars)"
