"""
Aegis GitHub Webhook Server
============================
A FastAPI server that listens for GitHub Pull Request events,
automatically runs the Aegis pipeline against changed files,
and posts the results back as a PR comment.

Usage:
    python github_webhook.py

Environment Variables:
    GITHUB_TOKEN:       Your GitHub Personal Access Token (for posting PR comments)
    GITHUB_WEBHOOK_SECRET: (Optional) Secret to validate webhook signatures
"""

import os
import sys
import json
import hmac
import hashlib
import tempfile
import subprocess
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import uvicorn

# ---------------------------------------------------------------------------
# App Initialization
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Aegis Security Webhook",
    description="Autonomous AI Security Pipeline - GitHub Integration",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
AEGIS_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Utility: Signature Verification
# ---------------------------------------------------------------------------
def verify_signature(payload_body: bytes, signature: str | None) -> bool:
    """Validate the GitHub webhook signature if a secret is configured."""
    if not WEBHOOK_SECRET:
        return True  # No secret configured, skip verification
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Utility: Post a comment on a GitHub PR
# ---------------------------------------------------------------------------
def post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> bool:
    """Posts a comment to a GitHub Pull Request via the REST API."""
    if not GITHUB_TOKEN:
        print("[Aegis Webhook] ⚠️  GITHUB_TOKEN not set – skipping PR comment.")
        return False

    import requests as _requests  # lazy import so server boots even without it

    url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    resp = _requests.post(url, headers=headers, json={"body": body}, timeout=15)
    if resp.status_code in (200, 201):
        print(f"[Aegis Webhook] ✅ Comment posted to PR #{pr_number}")
        return True
    else:
        print(f"[Aegis Webhook] ❌ Failed to post comment: {resp.status_code} {resp.text}")
        return False


# ---------------------------------------------------------------------------
# Utility: Run the Aegis pipeline on a file
# ---------------------------------------------------------------------------
def run_aegis_on_file(target_path: str) -> dict:
    """
    Invoke the orchestrator as a subprocess and capture its output.
    Returns a dict with keys: success, output, fixed_path.
    """
    cmd = [sys.executable, os.path.join(AEGIS_DIR, "orchestrator.py"), target_path]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        result = subprocess.run(
            cmd,
            cwd=AEGIS_DIR,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max for entire pipeline
            env=env,
        )
        output = result.stdout + "\n" + result.stderr
        success = result.returncode == 0
        fixed_path = target_path.replace(".py", "_secure.py")
        has_fix = os.path.exists(fixed_path)

        return {
            "success": success,
            "output": output.strip(),
            "fixed_path": fixed_path if has_fix else None,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Pipeline timed out after 5 minutes.", "fixed_path": None}
    except Exception as e:
        return {"success": False, "output": str(e), "fixed_path": None}


# ---------------------------------------------------------------------------
# Format the PR comment body
# ---------------------------------------------------------------------------
def format_comment(scan_result: dict, filename: str) -> str:
    """Build a rich Markdown comment for a GitHub PR."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_icon = "🟢" if scan_result["success"] else "🔴"

    lines = [
        f"## {status_icon} Aegis Security Scan Results",
        f"**File:** `{filename}`",
        f"**Timestamp:** {timestamp}",
        "",
    ]

    if scan_result["success"]:
        lines.append("✅ **No exploitable vulnerabilities detected** after full Red Team fuzzing.")
    else:
        lines.append("🔴 **Vulnerability detected and remediation attempted.**")

    lines += [
        "",
        "<details>",
        "<summary>📋 Pipeline Output (click to expand)</summary>",
        "",
        "```",
        scan_result["output"][-3000:],  # trim to avoid huge comments
        "```",
        "",
        "</details>",
    ]

    if scan_result.get("fixed_path"):
        lines += [
            "",
            f"🛡️ A secure patch has been generated at `{scan_result['fixed_path']}`.",
        ]
        try:
            with open(scan_result["fixed_path"], "r", encoding="utf-8") as f:
                fix_code = f.read()
            lines += [
                "",
                "<details>",
                "<summary>🔧 Proposed Secure Code (click to expand)</summary>",
                "",
                "```python",
                fix_code[:5000],
                "```",
                "",
                "</details>",
            ]
        except Exception:
            pass

    lines.append(f"\n---\n*Powered by Aegis AI Security Pipeline*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
async def health():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "Aegis Security Webhook",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
):
    """
    Main webhook endpoint.
    Listens for 'pull_request' events and scans changed Python files.
    """
    body = await request.body()

    # Verify signature
    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(body)
    event = x_github_event or "unknown"

    # We only care about pull_request events with action = opened / synchronize
    if event != "pull_request":
        return {"message": f"Ignored event type: {event}"}

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"message": f"Ignored PR action: {action}"}

    pr = payload.get("pull_request", {})
    pr_number = pr.get("number", 0)
    repo_full_name = payload.get("repository", {}).get("full_name", "")

    print(f"\n[Aegis Webhook] 🔔 PR #{pr_number} received on {repo_full_name} (action={action})")

    # In a production system, we would clone the repo / checkout the PR branch.
    # For this MVP, we scan files already in the Aegis workspace.
    target_files = []
    for f in os.listdir(AEGIS_DIR):
        if f.endswith(".py") and f not in (
            "orchestrator.py", "agent_red.py", "agent_blue.py",
            "sandbox.py", "context_loader.py", "github_webhook.py",
        ) and not f.endswith("_secure.py") and not f.startswith("generated_"):
            target_files.append(f)

    if not target_files:
        return {"message": "No scannable Python files found in workspace."}

    results = []
    for target in target_files:
        print(f"[Aegis Webhook] 🔍 Scanning: {target}")
        scan_result = run_aegis_on_file(target)
        comment_body = format_comment(scan_result, target)
        post_pr_comment(repo_full_name, pr_number, comment_body)
        results.append({"file": target, "vulnerable": not scan_result["success"]})

    return {"message": "Scan complete", "results": results}


@app.post("/scan")
async def manual_scan(request: Request):
    """
    Manual scan endpoint — POST a JSON body with {"file": "vuln_app.py"}.
    Useful for testing without GitHub.
    """
    body = await request.json()
    target = body.get("file")

    if not target:
        raise HTTPException(status_code=400, detail="Missing 'file' in request body")

    target_path = os.path.join(AEGIS_DIR, target)
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail=f"File {target} not found")

    print(f"[Aegis Webhook] 🔍 Manual scan triggered for: {target}")
    scan_result = run_aegis_on_file(target_path)

    return {
        "file": target,
        "success": scan_result["success"],
        "output": scan_result["output"][-3000:],
        "fixed_path": scan_result.get("fixed_path"),
    }


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("[AEGIS] SECURITY WEBHOOK SERVER")
    print("=" * 60)
    print(f"GitHub Token: {'[OK] Set' if GITHUB_TOKEN else '[!!] Not Set'}")
    print(f"Webhook Secret: {'[OK] Set' if WEBHOOK_SECRET else '[!!] Not Set (signatures not verified)'}")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8899)
