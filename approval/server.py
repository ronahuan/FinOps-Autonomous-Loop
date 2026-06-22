"""Approval server — handles Slack button clicks and link-based approvals.

Supports two modes:
  1. Slack interactive buttons (POST /slack/actions) — for Sandbox deployment
  2. Link-based approval (GET /approve?...) — for CRC deployment fallback

Both modes POST the approved intent to EDA, which triggers the Actor.
"""
from __future__ import annotations

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote_plus

import httpx
from dotenv import load_dotenv

load_dotenv()

EDA_URL = os.environ.get("EDA_WEBHOOK_URL", "")
EDA_USER = os.environ.get("EDA_WEBHOOK_USER", "")
EDA_PASS = os.environ.get("EDA_WEBHOOK_PASSWORD", "")

processed: set[str] = set()


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


def _update_slack_message(response_url: str, text: str) -> None:
    try:
        httpx.post(response_url, json={
            "replace_original": "true",
            "text": text,
        })
    except Exception:
        pass


def _proposal_key(intent: dict) -> str:
    return f"{intent.get('cluster')}__{intent.get('namespace')}__{intent.get('workload')}"


def _approve(intent: dict) -> tuple[int, str]:
    key = _proposal_key(intent)
    if key in processed:
        return 200, "Already processed — this proposal was already approved or denied."

    if intent.get("decision") != "approve":
        return 400, f"Cannot approve: decision is '{intent.get('decision')}', not 'approve'."

    intent["stage"] = "approved"
    status = _post_to_eda(intent)
    processed.add(key)
    return status, f"Approved: {intent.get('namespace')}/{intent.get('workload')}. Remediation triggered."


def _deny(intent: dict) -> str:
    key = _proposal_key(intent)
    processed.add(key)
    return f"Denied: {intent.get('namespace')}/{intent.get('workload')}. No changes will be made."


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

        if parsed.path == "/slack/actions":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            # Slack sends application/x-www-form-urlencoded with payload=<json>
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
            value = action.get("value", "{}")
            intent = json.loads(value)

            if action_id == "finops_approve":
                status, msg = _approve(intent)
                if response_url:
                    workload = f"{intent.get('namespace')}/{intent.get('workload')}"
                    saving = intent.get("monthly_saving_estimate", 0)
                    _update_slack_message(response_url,
                        f"Approved: {workload} (saving ${saving:.2f}/mo). Remediation triggered.")
            elif action_id == "finops_deny":
                msg = _deny(intent)
                if response_url:
                    workload = f"{intent.get('namespace')}/{intent.get('workload')}"
                    _update_slack_message(response_url,
                        f"Denied: {workload}. No changes will be made.")

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
