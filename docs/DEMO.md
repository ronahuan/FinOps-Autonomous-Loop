# FinOps Autonomous Loop — Demo

Two terminals. Five steps.

## Terminal 1 — Setup (run once, leave running)

```bash
./scripts/setup-demo.sh
```

Wait until you see `Waiting for events` — EDA is ready.

## Terminal 2 — The demo

### 1. Show the current resource requests

```bash
oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources}' | python3 -m json.tool
```

> "This workload requests 500m CPU and 512Mi memory but only runs sleep — it's wasting resources."

### 2. Run the loop

```bash
./scripts/run-loop.sh
```

This analyzes the workload, decides approve, and sends the proposal to EDA. **Check Slack** — a notification arrives with the recommendation and approve command.

### 3. Approve

```bash
python approve.py observer/out/proposals/finops-demo__waster.json
```

Watch Terminal 1 — the remediation playbook runs. Wait for it to finish (~60 seconds).

### 4. Show the new resource requests

```bash
oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources}' | python3 -m json.tool
```

> "Requests dropped from 500m/512Mi to 50m/64Mi. Limits are unchanged — the pod can still use its original resources if needed. We're saving ~$11/month on this workload."

### 5. Show the savings log

```bash
cat actor/out/savings.csv
```

## Reset

To run the demo again, stop EDA in Terminal 1 (`Ctrl+C`) and `source scripts/reset.sh`

## Optional: Rollback demo

After resetting, show what happens when a bad recommendation comes in.

### 1. Show the current limits

```bash
oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources}' | python3 -m json.tool
```

> "Limits are 500m CPU. Now imagine a bad recommendation says to set requests to 800m — that exceeds the limit."

### 2. Apply the bad recommendation

```bash
./scripts/rollback-demo.sh
```

The playbook tries to patch requests to 800m CPU. Kubernetes rejects it because requests can't exceed limits. The rescue block fires — it restores the original requests and suppresses the workload.

### 3. Show the rollback worked

```bash
oc get deploy waster -n finops-demo -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'
```

> Back to `{"cpu":"500m","memory":"512Mi"}` — the original values are restored.

```bash
cat actor/out/suppress.txt
```

> `finops-demo/waster` — the workload is suppressed so the same bad recommendation won't be applied again.

> "The automation caught the failure, rolled back to the original state, and blocked future attempts. No human intervention needed."
