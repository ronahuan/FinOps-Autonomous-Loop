#!/usr/bin/env bash
# Interactive FinOps Autonomous Loop Demo
# Run from the repo root: ./scripts/demo-interactive.sh

set +e

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RED="\033[31m"
RESET="\033[0m"

pause() {
  echo ""
  echo -e "${YELLOW}Press Enter to continue...${RESET}"
  read -r
}

run_cmd() {
  echo -e "${CYAN}\$ $1${RESET}"
  eval "$1"
  echo ""
}

header() {
  echo ""
  echo -e "${BOLD}════════════════════════════════════════════════════════════════${RESET}"
  echo -e "${BOLD}  $1${RESET}"
  echo -e "${BOLD}════════════════════════════════════════════════════════════════${RESET}"
  echo ""
}

# ── Setup ────────────────────────────────────────────────────────────────
header "FinOps Autonomous Loop — Interactive Demo"

echo "This demo shows how the FinOps autonomous loop detects over-provisioned"
echo "workloads, proposes right-sizing changes, and safely applies them with"
echo "auto-rollback on failure."
echo ""
echo "Loading environment..."
source scripts/env-actor.sh
source scripts/env-observer.sh
echo ""

# ── Step 1: Show the current cluster state ───────────────────────────────
header "STEP 1: Current Cluster State"

echo -e "${BOLD}The 'waster' deployment in finops-demo is our target workload.${RESET}"
echo "Let's see what it's currently requesting:"
echo ""

run_cmd "oc get deploy waster -n finops-demo"

pause

echo -e "${BOLD}Current resource requests and limits:${RESET}"
echo ""
run_cmd "oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources}' | python3 -m json.tool"

echo -e "${GREEN}→ Requesting 500m CPU and 512Mi memory${RESET}"
echo -e "${GREEN}→ But running 'sleep infinity' — actual usage is near zero${RESET}"
echo -e "${GREEN}→ This workload is wasting resources${RESET}"

pause

# ── Step 2: Show the RBAC scoping ────────────────────────────────────────
header "STEP 2: Security — Scoped Service Accounts"

echo -e "${BOLD}The automation uses two scoped service accounts, never the admin:${RESET}"
echo ""
echo "Observer (read-only):"
run_cmd "oc auth can-i get deployments -n finops-demo --as=system:serviceaccount:finops-demo:finops-observer"
run_cmd "oc auth can-i patch deployments -n finops-demo --as=system:serviceaccount:finops-demo:finops-observer"

echo "Actor (patch waster only):"
run_cmd "oc auth can-i patch deployments/waster -n finops-demo --as=system:serviceaccount:finops-demo:finops-actor"
run_cmd "oc auth can-i delete deployments/waster -n finops-demo --as=system:serviceaccount:finops-demo:finops-actor"
run_cmd "oc auth can-i patch deployments -n finops-demo --as=system:serviceaccount:finops-demo:finops-actor"

echo -e "${GREEN}→ Observer can read but not write${RESET}"
echo -e "${GREEN}→ Actor can only patch the 'waster' deployment — nothing else${RESET}"

pause

# ── Step 3: Run the Observer ─────────────────────────────────────────────
header "STEP 3: Observer — Analyze and Decide"

echo -e "${BOLD}The Observer reads the recommendation, checks the live cluster,${RESET}"
echo -e "${BOLD}and decides whether to approve or block the change.${RESET}"
echo ""
echo "Running the Observer now..."
echo ""

run_cmd "python3 -m observer.main 2>/dev/null"

echo -e "${GREEN}→ Decision: approve${RESET}"
echo -e "${GREEN}→ The recommendation passed all safety gates:${RESET}"
echo "   - Eligible (workload exists, has owner, has readiness probe, not crashing)"
echo "   - Fresh (recommendation is recent, not stale)"
echo "   - Material (saving > \$5/month, gap > 20%)"

pause

# ── Step 4: Show the proposal ────────────────────────────────────────────
header "STEP 4: The Proposal"

echo -e "${BOLD}The Observer wrote a proposal file with the intent:${RESET}"
echo ""
run_cmd "cat observer/out/proposals/finops-demo__waster.json"

echo -e "${GREEN}→ stage: 'proposed' — waiting for human approval${RESET}"
echo -e "${GREEN}→ decision: 'approve' — the Observer recommends this change${RESET}"
echo -e "${GREEN}→ current: 500m CPU / 512Mi → recommended: 50m CPU / 64Mi${RESET}"

pause

# ── Step 5: Show current state before patching ───────────────────────────
header "STEP 5: Before — Current Requests on the Cluster"

echo -e "${BOLD}Let's confirm the current state before we approve:${RESET}"
echo ""
echo "Requests:"
run_cmd "oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'"
echo ""
echo "Limits:"
run_cmd "oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources.limits}'"
echo ""

echo -e "${YELLOW}These are the values we're about to change (requests only, never limits).${RESET}"

pause

# ── Step 6: Start EDA ────────────────────────────────────────────────────
header "STEP 6: Start the Event-Driven Ansible Hub"

echo -e "${BOLD}EDA listens for events and triggers playbooks.${RESET}"
echo "Starting EDA in the background..."
echo ""

export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
unset KUBECONFIG
ansible-rulebook --rulebook eda/rulebooks/loop.yml -i actor/inventory/hosts.yml \
  --env-vars EDA_WEBHOOK_TOKEN,SLACK_WEBHOOK_URL --verbose > /tmp/eda-demo.log 2>&1 &
EDA_PID=$!

for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/endpoint -X POST \
    -H "Content-Type: application/json" -H "Authorization: Bearer ${EDA_WEBHOOK_TOKEN}" \
    -d '{"ping":true}' 2>/dev/null)
  if [ "$code" = "200" ]; then
    echo -e "${GREEN}EDA is ready and listening on port 5000${RESET}"
    break
  fi
  sleep 2
done

export KUBECONFIG=~/.crc/machines/crc/kubeconfig

pause

# ── Step 7: Approve ──────────────────────────────────────────────────────
header "STEP 7: Human Approval"

echo -e "${BOLD}A human reviews the proposal and approves it.${RESET}"
echo -e "${BOLD}This sends the approved intent to EDA, which triggers remediation.${RESET}"
echo ""
echo "Approving now..."
echo ""

run_cmd "python3 approve.py observer/out/proposals/finops-demo__waster.json"

echo -e "${GREEN}→ The intent was promoted from 'proposed' to 'approved'${RESET}"
echo -e "${GREEN}→ Posted to EDA — the remediation playbook is now running${RESET}"
echo ""
echo -e "${YELLOW}Waiting for the remediation playbook to complete (~60 seconds)...${RESET}"
echo "The playbook is:"
echo "  1. Backing up the current Deployment"
echo "  2. Patching requests from 500m/512Mi → 50m/64Mi"
echo "  3. Verifying the rollout completes successfully"
echo "  4. Recording savings"

sleep 65

pause

# ── Step 8: Show the result ──────────────────────────────────────────────
header "STEP 8: After — New Requests on the Cluster"

echo -e "${BOLD}Let's check what changed:${RESET}"
echo ""
echo "Requests:"
run_cmd "oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'"
echo ""
echo "Limits:"
run_cmd "oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources.limits}'"
echo ""

echo -e "${GREEN}→ Requests changed: 500m/512Mi → 50m/64Mi${RESET}"
echo -e "${GREEN}→ Limits unchanged: 500m/512Mi (we never touch limits)${RESET}"

pause

echo -e "${BOLD}Savings logged:${RESET}"
echo ""
run_cmd "cat actor/out/savings.csv"

echo -e "${BOLD}Backup created:${RESET}"
echo ""
run_cmd "ls -la actor/out/backups/ | tail -1"

echo -e "${GREEN}→ Estimated monthly saving: ~\$11.45${RESET}"
echo -e "${GREEN}→ Full Deployment backup stored for audit${RESET}"

pause

# ── Step 9: Rollback demo ───────────────────────────────────────────────
header "STEP 9: Rollback Demo — What Happens When It Fails"

echo -e "${BOLD}Now let's see the safety net. We'll reset the workload,${RESET}"
echo -e "${BOLD}apply a change, and force a post-patch failure.${RESET}"
echo ""

echo "Resetting to baseline..."
source scripts/reset.sh
oc rollout status deploy/waster -n finops-demo --timeout=120s 2>/dev/null

echo ""
echo "Current requests (back to baseline):"
run_cmd "oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'"

pause

echo -e "${BOLD}Running remediation with force_fail_after_patch=true${RESET}"
echo "This applies a valid patch, waits for rollout, then simulates a failure."
echo ""

unset KUBECONFIG
ansible-playbook actor/playbooks/remediate-safe.yml -i actor/inventory/hosts.yml \
  -e namespace=finops-demo -e workload=waster -e container=waster \
  -e cpu_req=50m -e mem_req=64Mi -e force_fail_after_patch=true 2>&1 | \
  grep -E "(SAFETY|Patch|Verify|force|ROLLBACK|ROLLED|Suppress|Remediation|ok=|changed=|failed=|rescued=)" || true
export KUBECONFIG=~/.crc/machines/crc/kubeconfig

echo ""

pause

header "STEP 10: After Rollback"

echo -e "${BOLD}The rollback restored the original requests:${RESET}"
echo ""
echo "Requests:"
run_cmd "oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'"
echo ""

echo -e "${BOLD}The workload is now suppressed (won't be proposed again until reset):${RESET}"
echo ""
run_cmd "cat actor/out/suppress.txt"

echo ""
echo -e "${GREEN}→ Requests restored to 500m/512Mi — the change was fully reversed${RESET}"
echo -e "${GREEN}→ Workload suppressed to prevent re-proposing a failing change${RESET}"
echo -e "${GREEN}→ Backup artifact preserved for audit${RESET}"

pause

# ── Cleanup ──────────────────────────────────────────────────────────────
header "Demo Complete"

echo "Summary:"
echo "  1. Observer analyzed the workload and approved right-sizing"
echo "  2. Human reviewed and approved the proposal"
echo "  3. Actor safely patched requests (not limits) with auto-rollback"
echo "  4. Savings logged, backup created"
echo "  5. Rollback demo proved the safety net works"
echo ""
echo "Key principles demonstrated:"
echo "  - Scoped RBAC (Observer reads, Actor patches waster only)"
echo "  - Human approval gate (no autonomous auto-apply)"
echo "  - Requests only (never limits)"
echo "  - Auto-rollback on any failure"
echo "  - Suppression after rollback"
echo ""

kill $EDA_PID 2>/dev/null
source scripts/reset.sh
echo ""
echo -e "${GREEN}Demo environment cleaned up and reset.${RESET}"
