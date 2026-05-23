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
from github_utils import clone_pr_branch, post_pr_comment, create_commit_on_pr

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
    # Also check parent dir since server might be run from inside aegis_core
    if not os.path.exists(reports_dir):
        reports_dir = os.path.join("..", ".aegis_reports")
        if not os.path.exists(reports_dir):
            # Fallback to local
            reports_dir = ".aegis_reports"
            os.makedirs(reports_dir, exist_ok=True)
        
    reports = []
    for filepath in glob.glob(os.path.join(reports_dir, "*.json")):
        try:
            with open(filepath, 'r') as f:
                reports.append(json.load(f))
        except Exception:
            pass
    # Sort by timestamp descending
    reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"reports": reports}

def process_pr_async(repo_full_name: str, pr_number: int):
    """
    Background task to run the full Aegis god-mode pipeline on a PR.
    """
    print(f"\n[Aegis - CI/CD] Starting async pipeline for PR #{pr_number} in {repo_full_name}")
    
    # 1. Clone PR branch
    temp_dir = tempfile.mkdtemp(prefix="aegis_")
    success = clone_pr_branch(repo_full_name, pr_number, temp_dir)
    if not success:
        print("[Aegis - CI/CD] Failed to clone PR branch.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    # 2. Run Hybrid Discovery (SAST)
    vulnerable_files = run_semgrep(temp_dir)
    
    if not vulnerable_files:
        print("[Aegis - CI/CD] No potential vulnerabilities found by SAST. Aegis pipeline stopping.")
        post_pr_comment(repo_full_name, pr_number, "🛡️ **Aegis God-Mode Analysis:** No vulnerabilities detected during SAST pre-scan. Code appears secure.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    # 3. Targeted Red/Blue Team execution
    fixed_files = []
    
    for target_file in vulnerable_files:
        print(f"\n[Aegis - CI/CD] Engaging God-Mode on flagged file: {target_file}")
        try:
            # We run orchestrator as a subprocess because it uses sys.exit()
            # which would kill our entire background worker thread.
            orchestrator_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "orchestrator.py"))
            
            result = subprocess.run(
                ["python", orchestrator_path, target_file],
                capture_output=True,
                text=True
            )
            
            # Write the orchestrator logs so developers can debug
            print(f"--- Orchestrator Output for {os.path.basename(target_file)} ---")
            print(result.stdout)
            if result.stderr:
                print("--- Error ---")
                print(result.stderr)
            
            secure_file_path = target_file.replace(".py", "_secure.py")
            if os.path.exists(secure_file_path):
                # Copy the secure file back over the original so we can commit it
                shutil.copy(secure_file_path, target_file)
                # Get relative path for git commits
                rel_file_path = os.path.relpath(target_file, temp_dir)
                fixed_files.append(rel_file_path)
                
        except Exception as e:
            print(f"[Aegis - CI/CD] Error running orchestrator on {target_file}: {e}")

    # 4. Commit patches back to PR
    if fixed_files:
        for f in fixed_files:
            create_commit_on_pr(temp_dir, f, f"🛡️ Aegis God-Mode: Secured {f}")
        
        post_pr_comment(
            repo_full_name, 
            pr_number, 
            f"🛡️ **Aegis God-Mode Analysis:** Found and verified vulnerabilities in {len(fixed_files)} files. Secure patches have been automatically committed."
        )
    else:
        post_pr_comment(
            repo_full_name, 
            pr_number, 
            "🛡️ **Aegis God-Mode Analysis:** Vulnerabilities flagged by SAST could not be verified by the Sandbox. No fixes required."
        )

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/github-webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks, x_hub_signature_256: str = Header(None)):
    """
    Listens for GitHub Pull Request events.
    When a PR is opened, it automatically triggers the multi-agent AI pipeline.
    """
    secret = os.environ.get("GITHUB_SECRET")
    if secret:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature")
            
        payload_body = await request.body()
        signature = 'sha256=' + hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(signature, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

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
            
            # Dispatch background task so we don't block the GitHub Webhook response
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
