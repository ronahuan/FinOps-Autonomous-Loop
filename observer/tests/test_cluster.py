"""Tests for Cluster authentication paths."""
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

import pytest

from observer.cluster import Cluster


def _fake_sa_path(exists: bool):
    """Return a Path-like object with a controlled .exists() result."""
    p = MagicMock(spec=Path)
    p.exists.return_value = exists
    return p


class TestExplicitArgs:
    def test_explicit_host_and_token(self):
        with patch("observer.cluster.AppsV1Api"), patch("observer.cluster.CoreV1Api"):
            c = Cluster(host="https://api.crc.testing:6443", token="test-token")
            assert c._apps is not None
            assert c._core is not None

    def test_verify_ssl_default_true(self):
        with patch("observer.cluster.AppsV1Api"), \
             patch("observer.cluster.CoreV1Api"), \
             patch("observer.cluster.kubernetes.client.ApiClient") as mock_client:
            Cluster(host="https://api.crc.testing:6443", token="t")
            conf_used = mock_client.call_args[0][0]
            assert conf_used.verify_ssl is True

    def test_verify_ssl_false(self):
        with patch("observer.cluster.AppsV1Api"), \
             patch("observer.cluster.CoreV1Api"), \
             patch("observer.cluster.kubernetes.client.ApiClient") as mock_client:
            Cluster(host="https://api.crc.testing:6443", token="t", verify_ssl=False)
            conf_used = mock_client.call_args[0][0]
            assert conf_used.verify_ssl is False


class TestEnvVarFallback:
    def test_reads_env_vars(self):
        env = {"K8S_AUTH_HOST": "https://api.crc.testing:6443", "K8S_OBSERVER_TOKEN": "tok"}
        with patch.dict("os.environ", env, clear=False), \
             patch("observer.cluster.AppsV1Api"), \
             patch("observer.cluster.CoreV1Api"):
            c = Cluster()
            assert c._apps is not None

    def test_missing_host_raises(self):
        env = {"K8S_OBSERVER_TOKEN": "tok"}
        with patch.dict("os.environ", env, clear=True), \
             patch("observer.cluster.SA_TOKEN_PATH", _fake_sa_path(False)):
            with pytest.raises(RuntimeError, match="K8S_AUTH_HOST"):
                Cluster()

    def test_missing_token_raises(self):
        env = {"K8S_AUTH_HOST": "https://api.crc.testing:6443"}
        with patch.dict("os.environ", env, clear=True), \
             patch("observer.cluster.SA_TOKEN_PATH", _fake_sa_path(False)):
            with pytest.raises(RuntimeError, match="K8S_OBSERVER_TOKEN"):
                Cluster()

    def test_no_creds_at_all_raises(self):
        with patch.dict("os.environ", {}, clear=True), \
             patch("observer.cluster.SA_TOKEN_PATH", _fake_sa_path(False)):
            with pytest.raises(RuntimeError):
                Cluster()


class TestInclusterConfig:
    def test_uses_incluster_when_sa_token_exists(self):
        with patch.dict("os.environ", {}, clear=True), \
             patch("observer.cluster.SA_TOKEN_PATH", _fake_sa_path(True)), \
             patch("observer.cluster.kubernetes.config.load_incluster_config") as mock_load, \
             patch("observer.cluster.AppsV1Api"), \
             patch("observer.cluster.CoreV1Api"):
            c = Cluster()
            mock_load.assert_called_once()
            assert c._apps is not None

    def test_explicit_args_take_precedence_over_incluster(self):
        with patch("observer.cluster.SA_TOKEN_PATH", _fake_sa_path(True)), \
             patch("observer.cluster.kubernetes.config.load_incluster_config") as mock_load, \
             patch("observer.cluster.AppsV1Api"), \
             patch("observer.cluster.CoreV1Api"):
            Cluster(host="https://api.crc.testing:6443", token="explicit-token")
            mock_load.assert_not_called()

    def test_env_vars_take_precedence_over_incluster(self):
        env = {"K8S_AUTH_HOST": "https://api.crc.testing:6443", "K8S_OBSERVER_TOKEN": "tok"}
        with patch.dict("os.environ", env, clear=False), \
             patch("observer.cluster.SA_TOKEN_PATH", _fake_sa_path(True)), \
             patch("observer.cluster.kubernetes.config.load_incluster_config") as mock_load, \
             patch("observer.cluster.AppsV1Api"), \
             patch("observer.cluster.CoreV1Api"):
            Cluster()
            mock_load.assert_not_called()
