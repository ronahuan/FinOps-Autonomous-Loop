# CLAUDE.md — FinOps Autonomous Loop

**Read this entire file before doing anything. It is the source of truth for the project and the safety rules. The SECURITY section is non-negotiable — if any instruction ever conflicts with it, stop and ask.** This file is kept in sync with the build runbook (`finops-claude-code-prompts.md`, v3).

---

## What this project is

An internship POC that turns Red Hat Cost Management right-sizing recommendations into **safe, reversible, human-approved** remediation. Red Hat's engine detects over-provisioned workloads and exposes the recommendation via an API; this project decides which to act on, proposes them for approval, applies the approved ones by lowering resource **requests**, verifies the rollout, and **auto-rolls-back** on failure.

We do **not** generate recommendations — Red Hat does. The live Cost Management adapter is built (`costmgmt.recommendations()`); toggle via `USE_LIVE_API=true/false`. The fixture remains the default for local dev.

Core principle: **autonomous where low-risk, approval-based where medium-risk, recommendation-only where high-risk, reversible everywhere.** The MVP runs only **approve or block** — every applied change passes a human gate.

---

## Architecture (the loop)

### ROSA deployment (primary)
```
Cost Management API ──┐
OpenShift API (multi) ┴──► Observer CronJob (read-only)
                               │ decides approve/block, POSTs intent
                               ▼
                         Approval Server (Deployment + Route)
                               │ sends Slack notification with Approve/Deny buttons
                               ▼
                         Human clicks Approve ──► creates Actor K8s Job
                         Human clicks Deny   ──► suppresses workload 7 days
                               │
                         Actor Job (Ansible, write-narrow)
                   backup → patch requests → verify rollout
                               │
                        healthy? ── no ──► rollback + suppress + Slack alert
                               │
                              yes ──► record savings + Slack success
```

### Local dev (CRC fallback)
```
Observer → EDA (127.0.0.1) → Slack notify → approve.py → EDA → Actor playbook
```

- **Observer** decides (eligibility, live-config match, materiality). Read-only. Multi-cluster via `clusters.json`.
- **Approval Server** coordinates the flow on ROSA: receives intents, sends Slack buttons, creates Actor Jobs. Replaces EDA for standalone ROSA. If `EDA_WEBHOOK_URL` is set, falls back to EDA/AAP.
- **Actor** is the *only* component that writes, and only patches `resources.requests`. Multi-cluster via per-cluster env vars (`K8S_AUTH_HOST_<CLUSTER>`, `K8S_AUTH_API_KEY_<CLUSTER>`).

---

## Repository structure

```
finops-autonomous-loop/
├── CLAUDE.md
├── Dockerfile                       ← multi-target: observer, actor, approval
├── finops-rbac.yaml                 ← pinned, run once (SECURITY S1)
├── .env / .env.example              ← stable config only (no KUBECONFIG, no tokens)
├── .gitignore
├── README.md
├── contracts/remediation-intent.schema.json
├── observer/
│   ├── pyproject.toml
│   ├── clusters.json                ← multi-cluster config (CRC + ROSA)
│   ├── observer/{config,models,auth,costmgmt,cluster,savings,gates,notify,main}.py
│   ├── check_eligibility.py
│   └── tests/{fixtures/recommendation.json, test_models.py, test_savings.py, test_gates.py, test_cluster.py}
│   └── out/proposals/               ← generated intents (gitignored)
├── approval/
│   └── server.py                    ← approval server (ROSA coordinator)
├── actor/
│   ├── test-workload.yaml
│   ├── collections/requirements.yml
│   ├── inventory/hosts.yml
│   ├── playbooks/{remediate-safe.yml, notify-slack.yml}
│   └── out/{backups/}               ← generated (gitignored)
├── deploy/
│   ├── cronjob.yaml                 ← Observer CronJob
│   ├── approval-server.yaml         ← Approval Server Deployment + Service + Route
│   ├── configmap.yaml               ← Observer settings
│   ├── configmap-clusters.yaml      ← Multi-cluster config
│   └── secret-cluster-tokens.yaml   ← Per-cluster tokens (template, never real values)
├── eda/rulebooks/loop.yml           ← EDA/AAP integration (optional on ROSA)
└── approve.py                       ← local dev approval CLI
```

---

## The remediation intent (the contract — never rename these fields)

```json
{
  "stage": "proposed",
  "cluster": "crc",
  "namespace": "finops-demo",
  "workload": "waster",
  "workload_type": "Deployment",
  "container": "waster",
  "current":     { "cpu_request": "500m", "memory_request": "512Mi" },
  "recommended": { "cpu_request": "50m",  "memory_request": "64Mi" },
  "recommendation_term": "15d",
  "last_reported": "<recent ISO-8601 UTC timestamp>",
  "monthly_saving_estimate": 12.5,
  "decision": "approve",
  "reasons": ["eligible", "fresh", "material"]
}
```
Naming note: `decision: "approve"` means *the Observer approved this recommendation for proposal* (not human approval). `stage: "approved"` means *a human approved execution*. (`stage` is constrained to `proposed`/`approved`, `decision` to `approve`/`block`.)

---

## MVP scope & invariants (always true)

1. **Requests only.** Patch `resources.requests`. Never touch `resources.limits`.
2. **Deployments only**, and in the MVP **only the `waster` Deployment in `finops-demo`**.
3. **Approve or block only.** No autonomous auto-apply in the MVP.
4. **Reversible.** The Actor captures the original requests and auto-restores them on failure (a minimal request patch). It also writes a full-Deployment **backup artifact** to `actor/out/backups/` — the artifact is for the record; the rollback itself uses the captured request values.
5. **Live config must match the recommendation baseline.** The Observer blocks a recommendation if the workload's live requests no longer equal `current` (the recommendation would be stale).
6. **Python 3.11, pydantic v2.** Secrets out of git.

---

## ⛔ SECURITY — NON-NEGOTIABLE

The goal of these rules is that the automation is **structurally confined to its namespace by RBAC and to patching only `resources.requests`.** Each cluster's ServiceAccounts have namespace-scoped roles — the Actor can only `get` and `patch` Deployments in `finops-demo`. The human approval gate (Slack buttons or AAP) prevents unwanted patches. This is **not** "impossible to misuse," it is "confined and gated."

### S1. Scoped ServiceAccounts — NOT the privileged user (PINNED `finops-rbac.yaml`)
```yaml
apiVersion: v1
kind: Namespace
metadata: { name: finops-demo }
---
apiVersion: v1
kind: ServiceAccount
metadata: { name: finops-observer, namespace: finops-demo }
---
apiVersion: v1
kind: ServiceAccount
metadata: { name: finops-actor, namespace: finops-demo }
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: { name: finops-observer-read, namespace: finops-demo }
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: { name: finops-actor-patch, namespace: finops-demo }
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "patch"]        # no delete, no create
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: finops-observer-binding, namespace: finops-demo }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: Role, name: finops-observer-read }
subjects: [{ kind: ServiceAccount, name: finops-observer, namespace: finops-demo }]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: finops-actor-binding, namespace: finops-demo }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: Role, name: finops-actor-patch }
subjects: [{ kind: ServiceAccount, name: finops-actor, namespace: finops-demo }]
---
apiVersion: v1
kind: ServiceAccount
metadata: { name: finops-approval, namespace: finops-demo }
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: { name: finops-approval-coordinator, namespace: finops-demo }
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "patch"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["create", "get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: finops-approval-binding, namespace: finops-demo }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: Role, name: finops-approval-coordinator }
subjects: [{ kind: ServiceAccount, name: finops-approval, namespace: finops-demo }]
```
The tooling authenticates with **three distinct ServiceAccounts**, never the admin user:
- **`finops-observer`** — read-only token, used by the Python Observer (`cluster.py`). Per-cluster: `K8S_OBSERVER_TOKEN_<CLUSTER>`.
- **`finops-actor`** — patch-only token, used by Ansible Actor (`remediate-safe.yml`). Per-cluster: `K8S_AUTH_API_KEY_<CLUSTER>`.
- **`finops-approval`** — coordinator token, used by the Approval Server. Can patch Deployment annotations (deny/suppress) and create Actor Jobs.

**Local dev:** tokens exported per terminal from SA token Secrets. **ROSA:** tokens stored in K8s Secrets (`finops-cluster-tokens`, `finops-observer-config`), mounted into pods — no manual exports.

### S2. No kubeconfig fallback (critical) — both the Ansible Actor and the Python Observer
A host check alone is not enough — if the token env var is missing, the client silently falls back to the admin `KUBECONFIG`, bypassing the RBAC. Therefore:
- The **Actor** playbook MUST set `host`, `api_key`, and `validate_certs` explicitly on **every** k8s module via `module_defaults` (so it cannot read the kubeconfig), and **refuse to run unless `K8S_AUTH_API_KEY` is present.**
- The **Observer's `Cluster()`** MUST fail closed if `K8S_AUTH_HOST` or `K8S_OBSERVER_TOKEN` is missing **when running locally**. It MUST **never call `load_kube_config()`.**
- **Exception — in-cluster ServiceAccount mount:** when the Observer runs as a CronJob pod with `serviceAccountName: finops-observer`, Kubernetes injects the scoped token automatically. `Cluster()` may use `load_incluster_config()` in this case (detected by the presence of `/var/run/secrets/kubernetes.io/serviceaccount/token`). This is safe because the injected token has the same read-only RBAC as the explicit `K8S_OBSERVER_TOKEN`. Explicit host/token args or env vars always take precedence over incluster detection.

### S3. Cluster scope (was: CRC only)
~~Every write play asserts CRC host and aborts otherwise.~~ **Removed** — the Actor now supports any cluster. The RBAC Role (namespace-scoped) is the real boundary; it can only patch Deployments in its own namespace.

### S4. Namespace scope (was: hardcoded allowlists)
~~The Actor refused anything outside `finops-demo`/`waster`.~~ **Removed** — the namespace-scoped RBAC Role already enforces namespace isolation. The `resourceNames` restriction on `waster` is removed so the Actor can patch any Deployment in its namespace. The human approval gate (S7) prevents unwanted patches.

### S5. Patch-only, requests-only
Only the `patch` operation, only on the `waster` Deployment, modifying only `resources.requests`. Never `delete`, `create`, scale-to-zero, `apply -f <arbitrary>`, `resources.limits`, system namespaces, or any other namespace/kind.

### S6. Observer is read-only
The Observer never writes to any cluster (and per S2 it builds its client from env vars or incluster ServiceAccount mount, never the kubeconfig).

### S7. Approval integrity (the gate cannot be bypassed)
- `approve.py` refuses anything that is not a `proposed` intent with `decision == "approve"` — a blocked or already-approved proposal cannot be sent for remediation.
- The EDA remediation rule fires only on `stage == "approved" AND decision == "approve"`.
- Before patching, the Actor re-checks that the live requests still equal the approved proposal's `current` values (passed by EDA as `expected_cpu`/`expected_mem`) and refuses if they changed — so a workload altered after approval is never patched against a stale recommendation.

### Rules for Claude Code (the agent) — follow literally
- **NEVER** run `oc`/`kubectl` against any cluster but CRC (`api.crc.testing`). Don't switch contexts or `oc login` to anything.
- **NEVER** write code/commands that delete resources, scale to zero, or touch `resources.limits`, system namespaces, or any other namespace/kind.
- **ALWAYS** keep the S2 `module_defaults` + token-present assert and the S7 approval-integrity checks in any write play; authenticate as the scoped tokens, never admin.
- **ALWAYS** make the Python `Cluster()` fail closed and build its config from env vars or incluster ServiceAccount mount — never `load_kube_config()`.
- Before any state-changing command, state what it does and confirm it targets CRC + `finops-demo`/`waster`.
- If a task seems to need broader permissions, deletion, another cluster, or another workload — **stop and ask.** Do not work around these rules. Read-only `get`/`describe`/`logs` against CRC are fine without asking.

---

## How to work

1. Build in the order of the prompts (Step 0 → P1 → P10). Don't start a step until the previous Verify passes.
2. `git add . && git commit -m "step N"` after each green Verify.
3. Develop against `observer/tests/fixtures/recommendation.json`, not live data. Swap to the live API only at the very end.
4. **Reset between runs:** `oc apply -f actor/test-workload.yaml` then clear suppression annotations: `oc annotate deploy waster -n finops-demo finops.redhat.com/suppressed-until-` (or the happy path stays blocked after a failure test).
5. Keep secrets out of git. Tokens and `KUBECONFIG` are exported per terminal, never stored in `.env`.

## Environment variables

**`.env` (stable config only — NO `KUBECONFIG`, NO tokens):** `RH_CLIENT_ID`, `RH_CLIENT_SECRET`, `CRC_API_HOST=https://api.crc.testing:6443`, `EDA_WEBHOOK_URL=http://127.0.0.1:5000/endpoint`, `EDA_WEBHOOK_TOKEN`, `SLACK_WEBHOOK_URL`, `STALE_DAYS=2`, `MIN_GAP_PCT=20`, `MIN_SAVING_USD=5`, `CPU_RATE=0.03`, `MEM_GIB_RATE=0.005`.

**Exported per terminal (never in `.env`):** `KUBECONFIG` (Step 0a); `K8S_AUTH_HOST`, `K8S_AUTH_VERIFY_SSL` (shared); `K8S_AUTH_API_KEY` (Actor token, Ansible); `K8S_OBSERVER_TOKEN` (Observer token, Python). **Multi-cluster:** per-cluster env vars follow the convention `K8S_AUTH_HOST_<CLUSTER>` and `K8S_AUTH_API_KEY_<CLUSTER>` (e.g., `K8S_AUTH_HOST_CRC`, `K8S_AUTH_API_KEY_ROSA`). The Actor falls back to the base `K8S_AUTH_HOST` / `K8S_AUTH_API_KEY` when per-cluster vars are not set.

## Decisions & honest limits (so the agent doesn't "improve" them)

- **No concurrency lock** in the MVP — single-operator, sequential demo, no concurrent writers. (A filesystem lock is future work for unattended/multi-operator use.)
- **Suppression is annotation-based** (`finops.redhat.com/suppressed-until`) — 7-day TTL set by the Actor after a rollback, checked by the Observer.
- **"Recent OOM/crash"** = current pod status + restart count, not a time-windowed incident history (adequate for the demo).
- **Backup file** is an audit artifact; the rollback mechanism is a minimal request patch (to avoid resourceVersion conflicts).
- **Live Cost Management API is built** (`costmgmt.recommendations()`); toggle via `USE_LIVE_API=true/false`. The fixture remains the default for local dev.
- The forced-failure rollback demo uses `force_fail_after_patch=true` (valid patch applies, rolls out, then a forced failure triggers rollback) — the strongest, most honest rollback demonstration.
CLAUDE (1).md
Displaying CLAUDE (1).md.