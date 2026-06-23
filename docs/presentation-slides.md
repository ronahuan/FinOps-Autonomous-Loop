# FinOps Autonomous Loop — Presentation

---

## Slide 1: The Problem

- Teams over-provision CPU and memory on OpenShift workloads
- Red Hat Cost Management detects waste and generates recommendations
- Recommendations sit in a dashboard — nobody acts on them
- Manual remediation doesn't scale

> **Speaker notes:** When teams deploy workloads on OpenShift, they tend to request more resources than they actually need — it's the safe thing to do. Red Hat Cost Management can detect this and generate right-sizing recommendations, but those recommendations just sit in the console. Nobody has time to review each one, figure out if it's safe, and manually patch the workload. That's what this project solves.

---

## Slide 2: What I Built

- Autonomous loop that turns recommendations into safe, reversible remediation
- Observer (Python) evaluates each recommendation through safety gates
- Actor (Ansible) patches workload resource requests after human approval
- Auto-rolls back on failure, suppresses for 7 days

**Core principle:** Autonomous where low-risk, approval-based where medium-risk, reversible everywhere

> **Speaker notes:** I built an end-to-end automation loop. A Python Observer pulls recommendations from the Cost Management API, runs them through eligibility and safety gates, and if everything passes, proposes the change for human approval via Slack. After a human approves in the AAP dashboard, an Ansible playbook patches the workload's resource requests — not limits, only requests. If anything goes wrong, it automatically rolls back to the original values and suppresses the workload so it's not retried for 7 days. The key design principle is that every change is reversible and requires human approval before execution.

---

## Slide 3: Architecture

```
Cost Management API  ──>  Observer (Python, read-only)
                               |  evaluates gates, decides approve/block
                               v
                          AAP Event Stream
                               |
                          EDA Controller (routes events)
                               |
                          Workflow Template
                            1. Notify Slack
                            2. Approval Node (human gate)
                            3. Remediate (Ansible)
                               |
                          Success? ── no ──> Rollback + Suppress
                               |
                              yes ──> Record savings
```

> **Speaker notes:** Here's how the components connect. The Observer pulls recommendations from the Cost Management API, evaluates them, and posts a remediation intent to AAP's Event Stream. The EDA Controller receives the event and triggers a Workflow Template. The workflow first sends a Slack notification with the recommendation details, then pauses at an Approval Node until a human approves in the AAP dashboard. Once approved, the remediation playbook runs — it patches the resource requests, verifies the rollout, and records savings. If the rollout fails at any point, the rescue block restores the original requests and suppresses the workload.

---

## Slide 4: Observer — Decision Gates

All five gates must pass for a recommendation to be approved:

- **Eligible** — Deployment exists, has owner label, readiness probe, no OOM/crashes, not suppressed
- **Fresh** — Reported within 2 days, term longer than 24 hours
- **Live config match** — Current requests still match what the recommendation expects
- **Material** — Resource gap > 20%, estimated saving > $5/month
- **Not suppressed** — Workload hasn't been suppressed from a previous failed remediation

> **Speaker notes:** The Observer is the brain — it's read-only and never writes to any cluster. Every recommendation goes through five gates. First, is the workload eligible? It needs to be a Deployment, it needs to exist, have an owner label and a readiness probe, no recent crashes, and not be suppressed. Second, is the recommendation fresh? If it's older than 2 days or based on less than 24 hours of data, we block it. Third, do the workload's current resource requests still match what the recommendation was based on? If someone already changed them, the recommendation is stale. Fourth, is the change material enough to bother? We need at least a 20% resource gap and $5/month in estimated savings. Finally, has this workload been suppressed from a previous failed attempt? If any gate fails, the recommendation is blocked with a reason.

---

## Slide 5: Actor — Safe Remediation

**Only component that writes, and only patches `resources.requests`**

- Scoped service account: can only patch the `waster` Deployment in `finops-demo`
- No kubeconfig fallback: refuses to run without explicit token
- Pre-patch baseline check: refuses if workload changed since approval
- On failure: auto-rollback to original requests + suppress 7 days
- Full Deployment backup saved before every patch

> **Speaker notes:** The Actor is an Ansible playbook with multiple safety layers. It uses a scoped service account that can only get and patch the specific waster Deployment — it can't list, delete, create, or touch anything else. Every Kubernetes module call has explicit host and token settings so it can never fall back to an admin kubeconfig. Before patching, it checks that the workload's current requests still match what was approved — if someone changed the workload between approval and execution, it refuses. It backs up the full Deployment, then patches only resource requests — never limits. If anything fails during the rollout, the rescue block fires: it restores the original requests and writes a suppression annotation so the Observer won't retry this workload for 7 days.

---

## Slide 6: Security Model

| Service Account | Permissions | Used by |
|----------------|------------|---------|
| finops-observer | get, list, watch Deployments + Pods | Python Observer |
| finops-actor | get, patch `waster` only | Ansible Actor |

- Never uses admin credentials — always scoped tokens
- Observer builds k8s client from env vars, never calls `load_kube_config()`
- Approval integrity: blocked intents cannot be sent for remediation

> **Speaker notes:** Security was a first-class concern from the start. There are two dedicated service accounts with minimal permissions. The Observer can only read — it gets, lists, and watches Deployments and Pods but can never write. The Actor can only get and patch the waster Deployment — that's it. Neither one uses the admin kubeconfig. The Observer builds its Kubernetes client explicitly from environment variables and fails if the token isn't set. The Actor's playbook has module_defaults that force the scoped token on every k8s call. And the approval gate can't be bypassed — a blocked or already-approved intent is rejected before it reaches the Actor.

---

## Slide 7: Live API + AAP Integration

**Cost Management API:**
- Authenticates via Red Hat SSO (client credentials)
- Pulls real recommendations, converts to Kubernetes quantities
- Toggle: `USE_LIVE_API=true` for production, `false` for development

**AAP Integration:**
- Event Stream receives Observer's webhook
- EDA Controller routes to Workflow Template
- Workflow: Slack notify -> Approval Node -> Remediate
- Approval link goes directly to AAP dashboard

> **Speaker notes:** The Observer connects to the real Cost Management API. It authenticates through Red Hat SSO using a service account's client ID and secret, then pulls the latest recommendations. The API returns CPU in cores and memory in bytes, so the Observer converts those to Kubernetes quantities like 500m and 512Mi. There's a toggle so I can switch between live API and fixture data during development. On the AAP side, I replaced the local EDA setup with a full AAP integration. The Observer posts to an Event Stream, the EDA Controller picks it up and triggers a Workflow Template. The workflow sends a Slack notification with the recommendation details and a link to approve in the AAP dashboard. Once someone approves, the remediation playbook runs automatically.

---

## Slide 8: State Management + Multi-Cluster

**Annotation-based state** (replaced file-based):
```
finops.redhat.com/suppressed-until: "2026-06-23T12:00:00Z"
finops.redhat.com/last-saving: "11.50"
finops.redhat.com/patched-cpu: "50m"
```
- Survives restarts, works across clusters, stays with the workload

**Multi-cluster support:**
- `clusters.json` maps cluster aliases to API hosts and tokens
- Observer matches each recommendation to its cluster
- One set of service account tokens per cluster

> **Speaker notes:** Originally I used local files for suppression and savings tracking, but those don't survive container restarts and don't work across clusters. I moved to Kubernetes annotations on the Deployment itself. The Actor writes suppression timestamps and savings data as annotations, and the Observer reads them. This keeps the Observer read-only while letting state live with the workload. For multi-cluster, there's a clusters.json config file that maps each cluster alias to its API host and token environment variable. The Observer loops through recommendations from the Cost Management API, matches each one to the right cluster, and connects using that cluster's credentials. Currently running on CRC with ROSA clusters being set up for multi-cluster testing.

---

## Slide 9: What Was Tested

| Scenario | Result |
|----------|--------|
| Happy path (fixture + live API) | Approve -> patch -> savings recorded |
| Stale/mismatched recommendation | Blocked with reason |
| OOM/crash or suppressed workload | Blocked |
| Forced failure | Auto-rollback + suppress 7 days |
| Full AAP workflow | Observer -> Slack -> Approve in AAP -> Remediate |

> **Speaker notes:** I tested both the happy path and failure scenarios. The happy path works end-to-end with both fixture data and the live Cost Management API — the Observer approves, posts to AAP, Slack notification arrives, human approves, workload gets patched, savings are recorded. For the blocking scenarios, stale recommendations, live config mismatches, workloads with OOM crashes, and suppressed workloads are all correctly blocked with clear reasons. For the rollback test, I use a forced failure flag that lets the patch succeed and roll out, then triggers a failure — the rescue block fires, restores the original requests, and suppresses the workload. The full AAP workflow has been tested end-to-end including the Slack notification and approval node.

---

## Slide 10: What I Learned

- **OpenShift:** CRC, ROSA, RBAC, service accounts, Cost Management API
- **AAP:** EDA Controller, Event Streams, Workflow Templates, Approval Nodes
- **FinOps:** Right-sizing patterns, cost-aware automation, safe remediation
- **Security-first design:** Scoped accounts, no kubeconfig fallback, approval integrity
- **Architecture tradeoffs:** Evaluated CronJob vs HCC Push vs rules engines

> **Speaker notes:** This project covered a lot of ground across the Red Hat ecosystem. I got hands-on with OpenShift through CRC and ROSA — RBAC, service accounts, the Cost Management API. On the automation side, I learned the full AAP stack including Event Driven Ansible with Event Streams and Workflow Templates with approval nodes. From a FinOps perspective, I learned how right-sizing works in practice and how to build automation that's safe enough to trust. The security model was a core focus — scoped service accounts, explicit token usage, and approval gates that can't be bypassed. I also evaluated different production architectures — CronJob polling, HCC Push webhooks, and even Red Hat Decision Manager as a rules engine — and made tradeoff decisions about what fits the MVP vs future state.

---

## Slide 11: Status & Next Steps

**Done:**
- Full end-to-end loop (Observer -> AAP -> Remediate -> Rollback)
- Live Cost Management API
- Annotation-based state (suppression + savings)
- Multi-cluster Observer design
- Comprehensive test coverage

**In progress:**
- ROSA clusters for multi-cluster testing

**Next:**
- CronJob deployment (Dockerfile, manifests)
- Failure notifications in Slack
- Multi-cluster end-to-end demo
