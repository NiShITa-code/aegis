import pytest
import os
import tempfile
from fastapi.testclient import TestClient
import hmac
import hashlib
import sys

# Ensure aegis_core is in path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from server import app

client = TestClient(app)

def test_webhook_missing_signature():
    os.environ["GITHUB_SECRET"] = "test_secret"
    response = client.post("/github-webhook", json={"action": "opened"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing signature"

def test_webhook_invalid_signature():
    os.environ["GITHUB_SECRET"] = "test_secret"
    response = client.post(
        "/github-webhook",
        json={"action": "opened"},
        headers={"x-hub-signature-256": "sha256=invalidhash"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid signature"

def test_webhook_valid_signature():
    secret = "test_secret"
    os.environ["GITHUB_SECRET"] = secret
    payload = b'{"action": "opened", "pull_request": {"number": 1}, "repository": {"full_name": "test/test"}}'
    
    signature = 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    response = client.post(
        "/github-webhook",
        content=payload,
        headers={"x-hub-signature-256": signature, "Content-Type": "application/json"}
    )
    assert response.status_code == 200
    assert "Aegis Pipeline Queued for PR #1" in response.json()["status"]
