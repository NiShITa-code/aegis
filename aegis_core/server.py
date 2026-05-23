from fastapi import FastAPI, Request, BackgroundTasks, Header, HTTPException
import uvicorn
import os
import tempfile
import shutil
import subprocess
import hmac
import hashlib
from dotenv import load_dotenv

# Local imports
from sast_scanner import run_semgrep
from github_utils import clone_pr_branch, post_pr_comment, apply_patch
from idempotency import store

load_dotenv()

app = FastAPI(title="Aegis AI Webhook Server")

from fastapi.middleware.cors import CORSMiddleware
import json
import glob

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/reports")
def get_reports():
    reports_dir = ".aegis_reports"
    if not os.path.exists(reports_dir):
        reports_dir = os.path.join("..", ".aegis_reports")
        if not os.path.exists(reports_dir):
            reports_dir = ".aegis_reports"
            os.makedirs(reports_dir, exist_ok=True)
        
    reports = []
    for filepath in glob.glob(os.path.join(reports_dir, "*.json")):
        try:
            with open(filepath, 'r') as f:
                reports.append(json.load(f))
        except Exception:
            pass
    reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"reports": reports}

def process_pr_async(repo_full_name: str, pr_number: int):
    print(f"\n[Aegis - CI/CD] Starting async pipeline for PR #{pr_number} in {repo_full_name}")
    
    temp_dir = tempfile.mkdtemp(prefix="aegis_")
    success = clone_pr_branch(repo_full_name, pr_number, temp_dir)
    if not success:
        print("[Aegis - CI/CD] Failed to clone PR branch.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    vulnerable_files = run_semgrep(temp_dir)
    
    if not vulnerable_files:
        print("[Aegis - CI/CD] No potential vulnerabilities found by SAST. Aegis pipeline stopping.")
        post_pr_comment(repo_full_name, pr_number, "🛡️ **Aegis God-Mode Analysis:** No vulnerabilities detected during SAST pre-scan. Code appears secure.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    fixed_files = []
    
    for target_file in vulnerable_files:
        print(f"\n[Aegis - CI/CD] Engaging God-Mode on flagged file: {target_file}")
        try:
            orchestrator_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "orchestrator.py"))
            
            result = subprocess.run(
                ["python", orchestrator_path, target_file],
                capture_output=True,
                text=True
            )
            
            print(f"--- Orchestrator Output for {os.path.basename(target_file)} ---")
            print(result.stdout)
            if result.stderr:
                print("--- Error ---")
                print(result.stderr)
            
            if result.returncode == 0:
                secure_file_path = target_file.replace(".py", "_secure.py")
                if os.path.exists(secure_file_path):
                    shutil.copy(secure_file_path, target_file)
                    rel_file_path = os.path.relpath(target_file, temp_dir)
                    fixed_files.append(rel_file_path)
            else:
                print(f"[Aegis - CI/CD] Orchestrator failed to secure {target_file}. Skipping commit.")
                
        except Exception as e:
            print(f"[Aegis - CI/CD] Error running orchestrator on {target_file}: {e}")

    if fixed_files:
        success = apply_patch(temp_dir, fixed_files, "🛡️ Aegis God-Mode: Secured vulnerabilities", repo_full_name, pr_number)
        if not success:
            print("[Aegis - CI/CD] Failed to push or create PR for the patch.")
    else:
        post_pr_comment(
            repo_full_name, 
            pr_number, 
            "🛡️ **Aegis God-Mode Analysis:** Vulnerabilities flagged by SAST could not be verified by the Sandbox. No fixes required."
        )

    shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/github-webhook")
async def github_webhook(
    request: Request, 
    background_tasks: BackgroundTasks, 
    x_hub_signature_256: str = Header(None),
    x_github_delivery: str = Header(None)
):
    secret = os.environ.get("GITHUB_SECRET")
    if secret:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature")
            
        payload_body = await request.body()
        signature = 'sha256=' + hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(signature, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_delivery and store.is_processed(x_github_delivery):
        return {"status": "Already processed."}

    try:
        data = await request.json()
        action = data.get("action")
        
        if action in ["opened", "synchronize", "reopened"]:
            pr = data.get("pull_request", {})
            pr_number = pr.get("number")
            repo = data.get("repository", {})
            repo_full_name = repo.get("full_name")
            
            if not pr_number or not repo_full_name:
                return {"status": "Error: Missing PR number or repo name."}
                
            print(f"\n[Aegis - CI/CD] 🚨 GitHub PR #{pr_number} Updated. Queuing Async Analysis...")
            
            if x_github_delivery:
                store.mark_processed(x_github_delivery)
            
            background_tasks.add_task(process_pr_async, repo_full_name, pr_number)
                
            return {"status": f"Aegis Pipeline Queued for PR #{pr_number}"}
            
        return {"status": "Ignored - Event not actionable."}
    except Exception as e:
        print(f"[Aegis - CI/CD] Webhook Error: {e}")
        return {"error": str(e)}

@app.get("/health")
def health_check():
    return {"status": "Aegis God-Mode is actively listening for commits."}

if __name__ == "__main__":
    print("=========================================================")
    print("🛡️ AEGIS GITHUB WEBHOOK LISTENER STARTING...")
    print("Listening on http://0.0.0.0:8000/github-webhook")
    print("=========================================================")
    uvicorn.run(app, host="0.0.0.0", port=8000)
