"""Approval server — coordinates the FinOps loop on ROSA.

Replaces EDA as the event coordinator:
  - POST /intent       — receives proposed intents from the Observer
  - POST /slack/actions — handles Slack approve/deny button clicks
  - GET  /approve       — link-based approval fallback
  - GET  /deny          — link-based deny fallback
  - GET  /health        — readiness probe

On approve: creates an Actor K8s Job (or POSTs to EDA if configured).
On deny: suppresses the workload for 7 days via annotation.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote_plus

import httpx
from dotenv import load_dotenv

load_dotenv()

EDA_URL = os.environ.get("EDA_WEBHOOK_URL", "")
EDA_USER = os.environ.get("EDA_WEBHOOK_USER", "")
EDA_PASS = os.environ.get("EDA_WEBHOOK_PASSWORD", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
ACTOR_IMAGE = os.environ.get("ACTOR_IMAGE", "quay.io/pm_ronahuan/finops-actor:latest")
ACTOR_JOB_NAMESPACE = os.environ.get("ACTOR_JOB_NAMESPACE", "finops-demo")

pending_intents: dict[str, dict] = {}
processed: set[str] = set()


def _proposal_key(intent: dict) -> str:
    return f"{intent.get('cluster', '')}__{intent.get('namespace', '')}__{intent.get('workload', '')}"


# ---------------------------------------------------------------------------
# Slack notifications
# ---------------------------------------------------------------------------

def _send_slack_notification(intent: dict) -> None:
    if not SLACK_WEBHOOK_URL:
        print("[approval] SLACK_WEBHOOK_URL not set — skipping notification")
        return

    key = _proposal_key(intent)
    cluster = intent.get("cluster", "unknown")
    ns = intent.get("namespace", "")
    wl = intent.get("workload", "")
    saving = intent.get("monthly_saving_estimate", 0)
    cur = intent.get("current", {})
    rec = intent.get("recommended", {})

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "FinOps Right-Size Proposal"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Cluster:*\n{cluster}"},
            {"type": "mrkdwn", "text": f"*Workload:*\n{ns}/{wl}"},
        ]},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Estimated Saving:*\n${saving:.2f}/mo"},
        ]},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Current:*\nCPU {cur.get('cpu_request')}, Mem {cur.get('memory_request')}"},
            {"type": "mrkdwn", "text": f"*Recommended:*\nCPU {rec.get('cpu_request')}, Mem {rec.get('memory_request')}"},
        ]},
        {"type": "actions", "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Approve"},
                "style": "primary",
                "action_id": "finops_approve",
                "value": key,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Deny"},
                "style": "danger",
                "action_id": "finops_deny",
                "value": key,
            },
        ]},
    ]

    try:
        httpx.post(SLACK_WEBHOOK_URL, json={"blocks": blocks, "text": f"FinOps Proposal: {ns}/{wl}"})
    except Exception as e:
        print(f"[approval] Slack POST failed: {e}")


def _update_slack_message(response_url: str, text: str) -> None:
    try:
        httpx.post(response_url, json={"replace_original": "true", "text": text})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# K8s helpers — deny-path suppression + Actor Job creation
# ---------------------------------------------------------------------------

def _get_k8s_apps_client(cluster: str):
    """Build a K8s AppsV1Api client for the target cluster."""
    import kubernetes.client
    import kubernetes.config

    host_key = f"K8S_AUTH_HOST_{cluster.upper()}"
    token_key = f"K8S_AUTH_API_KEY_{cluster.upper()}"
    host = os.environ.get(host_key, os.environ.get("K8S_AUTH_HOST", ""))
    token = os.environ.get(token_key, os.environ.get("K8S_AUTH_API_KEY", ""))

    if host and token:
        conf = kubernetes.client.Configuration()
        conf.host = host
        conf.verify_ssl = False
        api_client = kubernetes.client.ApiClient(conf)
        api_client.set_default_header("Authorization", f"Bearer {token}")
        return kubernetes.client.AppsV1Api(api_client)

    try:
        kubernetes.config.load_incluster_config()
        return kubernetes.client.AppsV1Api()
    except Exception:
        return None


def _suppress_workload(cluster: str, namespace: str, workload: str) -> bool:
    apps_api = _get_k8s_apps_client(cluster)
    if not apps_api:
        print(f"[approval] No K8s client for cluster '{cluster}' — suppression skipped")
        return False

    suppress_until = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        apps_api.patch_namespaced_deployment(
            name=workload,
            namespace=namespace,
            body={"metadata": {"annotations": {
                "finops.redhat.com/suppressed-until": suppress_until,
                "finops.redhat.com/denied-by": "human",
                "finops.redhat.com/denied-at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }}},
        )
        print(f"[approval] Suppressed {namespace}/{workload} until {suppress_until}")
        return True
    except Exception as e:
        print(f"[approval] Failed to annotate {namespace}/{workload}: {e}")
        return False


def _create_actor_job(intent: dict) -> tuple[int, str]:
    import kubernetes.client
    import kubernetes.config

    cluster = intent.get("cluster", "")
    ns = intent.get("namespace", "")
    wl = intent.get("workload", "")
    container = intent.get("container", "")
    cur = intent.get("current", {})
    rec = intent.get("recommended", {})
    saving = intent.get("monthly_saving_estimate", 0)

    job_name = f"finops-actor-{wl}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"[:63]

    try:
        kubernetes.config.load_incluster_config()
        batch_api = kubernetes.client.BatchV1Api()
    except Exception as e:
        return 500, f"Cannot create Job (not in-cluster?): {e}"

    extra_vars = json.dumps({
        "cluster": cluster,
        "namespace": ns,
        "workload": wl,
        "container": container,
        "cpu_req": rec.get("cpu_request"),
        "mem_req": rec.get("memory_request"),
        "expected_cpu": cur.get("cpu_request"),
        "expected_mem": cur.get("memory_request"),
        "saving": str(saving),
        "slack_webhook_url": SLACK_WEBHOOK_URL,
    })

    job = kubernetes.client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=kubernetes.client.V1ObjectMeta(
            name=job_name,
            namespace=ACTOR_JOB_NAMESPACE,
            labels={"app": "finops-actor", "finops.redhat.com/workload": wl},
        ),
        spec=kubernetes.client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=3600,
            template=kubernetes.client.V1PodTemplateSpec(
                spec=kubernetes.client.V1PodSpec(
                    service_account_name="finops-actor",
                    restart_policy="Never",
                    containers=[
                        kubernetes.client.V1Container(
                            name="actor",
                            image=ACTOR_IMAGE,
                            command=["ansible-playbook", "playbooks/remediate-safe.yml", "-e", extra_vars],
                            env_from=[
                                kubernetes.client.V1EnvFromSource(
                                    secret_ref=kubernetes.client.V1SecretEnvSource(name="finops-cluster-tokens")
                                ),
                            ],
                            env=[
                                kubernetes.client.V1EnvVar(name="SLACK_WEBHOOK_URL", value=SLACK_WEBHOOK_URL),
                            ],
                        ),
                    ],
                ),
            ),
        ),
    )

    try:
        batch_api.create_namespaced_job(namespace=ACTOR_JOB_NAMESPACE, body=job)
        print(f"[approval] Created Actor Job '{job_name}' for {ns}/{wl}")
        return 200, f"Approved: {ns}/{wl}. Actor Job '{job_name}' created."
    except Exception as e:
        print(f"[approval] Failed to create Actor Job: {e}")
        return 500, f"Failed to create Actor Job: {e}"


# ---------------------------------------------------------------------------
# EDA integration (backward compat)
# ---------------------------------------------------------------------------

def _post_to_eda(intent: dict) -> int:
    if not EDA_URL:
        print("[approval] EDA_WEBHOOK_URL not set — skipping POST")
        return 200
    auth = (EDA_USER, EDA_PASS) if EDA_USER else None
    try:
        resp = httpx.post(EDA_URL, json=intent, auth=auth)
        return resp.status_code
    except Exception as e:
        print(f"[approval] EDA POST failed: {e}")
        return 502


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _approve(intent: dict) -> tuple[int, str]:
    key = _proposal_key(intent)
    if key in processed:
        return 200, "Already processed — this proposal was already approved or denied."

    if intent.get("decision") != "approve":
        return 400, f"Cannot approve: decision is '{intent.get('decision')}', not 'approve'. (S7)"

    intent["stage"] = "approved"
    processed.add(key)

    if EDA_URL:
        status = _post_to_eda(intent)
        return status, f"Approved: {intent.get('namespace')}/{intent.get('workload')}. Remediation triggered via EDA."

    return _create_actor_job(intent)


def _deny(intent: dict) -> str:
    key = _proposal_key(intent)
    if key in processed:
        return "Already processed — this proposal was already approved or denied."

    processed.add(key)
    cluster = intent.get("cluster", "")
    ns = intent.get("namespace", "")
    wl = intent.get("workload", "")

    suppressed = _suppress_workload(cluster, ns, wl)
    suffix = " Suppressed for 7 days." if suppressed else ""
    return f"Denied: {ns}/{wl}.{suffix}"


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

def _html(title: str, message: str, success: bool = True) -> bytes:
    color = "#2ea44f" if success else "#d73a49"
    return f"""<!DOCTYPE html>
<html><head><title>{title}</title>
<style>body{{font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f6f8fa}}
.card{{background:white;border-radius:12px;padding:40px;box-shadow:0 1px 3px rgba(0,0,0,.12);text-align:center;max-width:400px}}
h1{{color:{color};margin:0 0 12px}}p{{color:#57606a;margin:0}}</style></head>
<body><div class="card"><h1>{title}</h1><p>{message}</p></div></body></html>""".encode()


class ApprovalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._respond(200, "ok")
            return

        if parsed.path == "/approve":
            intent = self._intent_from_params(params)
            if not intent:
                self._respond_html(400, "Bad Request", "Missing required parameters.", False)
                return
            status, msg = _approve(intent)
            self._respond_html(200, "Approved" if status < 400 else "Error", msg, status < 400)
            return

        if parsed.path == "/deny":
            intent = self._intent_from_params(params)
            msg = _deny(intent) if intent else "Denied."
            self._respond_html(200, "Denied", msg, False)
            return

        self._respond(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))

        if parsed.path == "/intent":
            body = json.loads(self.rfile.read(length).decode())

            if body.get("decision") != "approve":
                self._respond(200, f"Intent blocked by Observer: {body.get('reasons')}")
                return

            key = _proposal_key(body)
            if key in processed:
                self._respond(200, f"Already processed: {key}")
                return

            pending_intents[key] = body
            _send_slack_notification(body)
            print(f"[approval] Received intent: {key}")
            self._respond(200, f"Intent received: {key}")
            return

        if parsed.path == "/slack/actions":
            body = self.rfile.read(length).decode()
            payload_str = ""
            for part in body.split("&"):
                if part.startswith("payload="):
                    payload_str = unquote_plus(part[8:])
                    break

            if not payload_str:
                self._respond(400, "Missing payload")
                return

            payload = json.loads(payload_str)
            actions = payload.get("actions", [])
            response_url = payload.get("response_url", "")

            if not actions:
                self._respond(200, "")
                return

            action = actions[0]
            action_id = action.get("action_id", "")
            key = action.get("value", "")
            intent = pending_intents.get(key)

            if not intent:
                if response_url:
                    _update_slack_message(response_url, f"Intent expired or already processed: {key}")
                self._respond(200, "")
                return

            if action_id == "finops_approve":
                status, msg = _approve(intent)
                if response_url:
                    wl = f"{intent.get('namespace')}/{intent.get('workload')}"
                    saving = intent.get("monthly_saving_estimate", 0)
                    _update_slack_message(response_url,
                        f"Approved: {wl} (saving ${saving:.2f}/mo). Remediation triggered.")
            elif action_id == "finops_deny":
                msg = _deny(intent)
                if response_url:
                    wl = f"{intent.get('namespace')}/{intent.get('workload')}"
                    _update_slack_message(response_url,
                        f"Denied: {wl}. Suppressed for 7 days.")

            pending_intents.pop(key, None)
            self._respond(200, "")
            return

        self._respond(404, "Not found")

    def _intent_from_params(self, params: dict) -> dict | None:
        required = ["namespace", "workload", "container", "current_cpu", "current_mem", "rec_cpu", "rec_mem"]
        if not all(k in params for k in required):
            return None
        return {
            "stage": "proposed",
            "decision": "approve",
            "cluster": params.get("cluster", ["unknown"])[0],
            "namespace": params["namespace"][0],
            "workload": params["workload"][0],
            "workload_type": params.get("workload_type", ["Deployment"])[0],
            "container": params["container"][0],
            "current": {
                "cpu_request": params["current_cpu"][0],
                "memory_request": params["current_mem"][0],
            },
            "recommended": {
                "cpu_request": params["rec_cpu"][0],
                "memory_request": params["rec_mem"][0],
            },
            "recommendation_term": params.get("term", ["1d"])[0],
            "last_reported": params.get("last_reported", [""])[0],
            "monthly_saving_estimate": float(params.get("saving", ["0"])[0]),
            "reasons": ["eligible", "fresh", "material"],
        }

    def _respond(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def _respond_html(self, code: int, title: str, message: str, success: bool):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_html(title, message, success))

    def log_message(self, format, *args):
        print(f"[approval] {args[0]}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8085"))
    server = HTTPServer(("0.0.0.0", port), ApprovalHandler)
    print(f"Approval server listening on port {port}")
    server.serve_forever()
