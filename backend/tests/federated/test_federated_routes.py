"""Tests for the /federated blueprint.

All upstream HTTP calls are mocked — no live FedDeepInsight service required.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests as req_lib


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None):
    """Build a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFederatedInputValidation:
    """Routes that validate required query params before hitting upstream."""

    def test_state_missing_model_id(self, client):
        resp = client.get("/federated/state")
        assert resp.status_code == 400
        assert b"model_id" in resp.data

    def test_model_missing_model_id(self, client):
        resp = client.get("/federated/model")
        assert resp.status_code == 400
        assert b"model_id" in resp.data


class TestFederatedUnauthenticated:
    """UI route requires login."""

    def test_ui_redirects_when_not_logged_in(self, client):
        resp = client.get("/federated/ui")
        assert resp.status_code == 302


class TestFederatedProxying:
    """Routes that forward to the FedDeepInsight service."""

    @patch("requests.request")
    def test_register_forwards_payload(self, mock_req, client):
        mock_req.return_value = _mock_response(200, {"status": "registered"})
        resp = client.post(
            "/federated/register",
            json={"client_id": "c1"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "registered"
        mock_req.assert_called_once()

    @patch("requests.request")
    def test_update_forwards_payload(self, mock_req, client):
        mock_req.return_value = _mock_response(200, {"ack": True})
        resp = client.post(
            "/federated/update",
            json={"model_id": "m1", "round": 1, "weights": []},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["ack"] is True

    @patch("requests.request")
    def test_aggregate_forwards_payload(self, mock_req, client):
        mock_req.return_value = _mock_response(200, {"aggregated": True})
        resp = client.post(
            "/federated/aggregate",
            json={"model_id": "m1", "round": 1},
            content_type="application/json",
        )
        assert resp.status_code == 200

    @patch("requests.request")
    def test_state_forwards_with_model_id(self, mock_req, client):
        mock_req.return_value = _mock_response(
            200,
            {"model_id": "m1", "round": 0, "status": "idle", "participating_clients": 0},
        )
        resp = client.get("/federated/state?model_id=m1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["model_id"] == "m1"

    @patch("requests.request")
    def test_model_forwards_with_model_id(self, mock_req, client):
        mock_req.return_value = _mock_response(
            200, {"model_id": "m1", "round": 0, "weights": [0.1]}
        )
        resp = client.get("/federated/model?model_id=m1")
        assert resp.status_code == 200
        assert resp.get_json()["weights"] == [0.1]


class TestFederatedUpstreamErrors:
    """Upstream connectivity failures return 503."""

    @patch("requests.request")
    def test_connection_error_returns_503(self, mock_req, client):
        mock_req.side_effect = req_lib.exceptions.ConnectionError
        resp = client.get("/federated/state?model_id=m1")
        assert resp.status_code == 503
        assert b"unavailable" in resp.data

    @patch("requests.request")
    def test_timeout_returns_503(self, mock_req, client):
        mock_req.side_effect = req_lib.exceptions.Timeout
        resp = client.get("/federated/model?model_id=m1")
        assert resp.status_code == 503
        assert b"unavailable" in resp.data
