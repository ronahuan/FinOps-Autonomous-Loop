"""Kubernetes cluster client — read-only, scoped to finops-observer token.

SECURITY (S2, S6): builds its Configuration explicitly from env vars.
Never calls load_kube_config() or load_incluster_config().
"""
from __future__ import annotations

import os

import kubernetes.client
from kubernetes.client import AppsV1Api, CoreV1Api


class Cluster:
    def __init__(self) -> None:
        host = os.environ.get("K8S_AUTH_HOST")
        token = os.environ.get("K8S_OBSERVER_TOKEN")
        if not host:
            raise RuntimeError("K8S_AUTH_HOST is not set — refusing to start (S2)")
        if not token:
            raise RuntimeError("K8S_OBSERVER_TOKEN is not set — refusing to start (S2)")

        verify_ssl = os.environ.get("K8S_AUTH_VERIFY_SSL", "true").lower() not in ("false", "0", "no")

        conf = kubernetes.client.Configuration()
        conf.host = host
        conf.verify_ssl = verify_ssl

        api_client = kubernetes.client.ApiClient(conf)
        api_client.set_default_header("Authorization", f"Bearer {token}")
        self._apps = AppsV1Api(api_client)
        self._core = CoreV1Api(api_client)

    def workload_facts(self, namespace: str, workload: str, container: str) -> dict:
        try:
            dep = self._apps.read_namespaced_deployment(workload, namespace)
        except kubernetes.client.ApiException as e:
            if e.status == 404:
                return {
                    "exists": False,
                    "owner_label": "",
                    "has_readiness_probe": False,
                    "recent_oom_or_crash": False,
                    "live_cpu_request": "",
                    "live_mem_request": "",
                }
            raise

        labels = dep.metadata.labels or {}
        owner_label = labels.get("owner", "")

        has_readiness_probe = False
        live_cpu_request = ""
        live_mem_request = ""
        for c in dep.spec.template.spec.containers:
            if c.name == container:
                has_readiness_probe = c.readiness_probe is not None
                if c.resources and c.resources.requests:
                    live_cpu_request = c.resources.requests.get("cpu", "")
                    live_mem_request = c.resources.requests.get("memory", "")
                break

        pods = self._core.list_namespaced_pod(
            namespace, label_selector=f"app={workload}",
        )
        recent_oom_or_crash = False
        for pod in pods.items:
            if not pod.status or not pod.status.container_statuses:
                continue
            for cs in pod.status.container_statuses:
                if cs.restart_count and cs.restart_count > 3:
                    recent_oom_or_crash = True
                if (
                    cs.last_state
                    and cs.last_state.terminated
                    and cs.last_state.terminated.reason == "OOMKilled"
                ):
                    recent_oom_or_crash = True

        return {
            "exists": True,
            "owner_label": owner_label,
            "has_readiness_probe": has_readiness_probe,
            "recent_oom_or_crash": recent_oom_or_crash,
            "live_cpu_request": live_cpu_request,
            "live_mem_request": live_mem_request,
        }
