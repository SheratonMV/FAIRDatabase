import os

import requests
from flask import Blueprint, jsonify, render_template, request, session

from src.auth.decorators import login_required

routes = Blueprint("federated_routes", __name__)

FED_API_BASE = os.environ.get("FED_API_BASE", "http://localhost:7070")


def _forward(method, path, *, params=None, json_body=None):
    """Forward a request to the FedDeepInsight service and proxy the response."""
    headers = {}
    auth = request.headers.get("Authorization")
    if auth:
        headers["Authorization"] = auth

    url = f"{FED_API_BASE}{path}"
    try:
        resp = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=10,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return jsonify({"error": "Federated learning service unavailable"}), 503

    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    return jsonify(data), resp.status_code


@routes.route("/register", methods=["POST"])
def register():
    payload = request.get_json(silent=True) or {}
    return _forward("POST", "/federated/register", json_body=payload)


@routes.route("/model", methods=["GET"])
def model():
    model_id = request.args.get("model_id")
    if not model_id:
        return jsonify({"error": "model_id is required"}), 400

    params = {"model_id": model_id}
    round_number = request.args.get("round")
    if round_number is not None:
        params["round"] = round_number
    return _forward("GET", "/federated/model", params=params)


@routes.route("/update", methods=["POST"])
def update():
    payload = request.get_json(silent=True) or {}
    return _forward("POST", "/federated/update", json_body=payload)


@routes.route("/aggregate", methods=["POST"])
def aggregate():
    payload = request.get_json(silent=True) or {}
    return _forward("POST", "/federated/aggregate", json_body=payload)


@routes.route("/state", methods=["GET"])
def state():
    model_id = request.args.get("model_id")
    if not model_id:
        return jsonify({"error": "model_id is required"}), 400
    return _forward("GET", "/federated/state", params={"model_id": model_id})


@routes.route("/ui", methods=["GET"])
@login_required()
def federated_ui():
    return (
        render_template(
            "federated_learning/federated_learning.html",
            model_id="federated-learning",
            user_email=session.get("email"),
            current_path=request.path,
        ),
        200,
    )
