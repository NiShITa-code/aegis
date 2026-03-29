from fastapi import FastAPI, Request
from orchestrator import run_aegis_pipeline
import uvicorn
import os

app = FastAPI(title="Aegis AI Webhook Server")

@app.post("/github-webhook")
async def github_webhook(request: Request):
    """
    Listens for GitHub Pull Request events.
    When a PR is opened, it automatically triggers the multi-agent AI pipeline.
    """
    try:
        data = await request.json()
        action = data.get("action")
        
        # We only care when a developer opens a PR or updates code
        if action in ["opened", "synchronize", "reopened"]:
            pr_number = data.get("pull_request", {}).get("number", "Unknown")
            print(f"\n[Aegis - CI/CD Integration] 🚨 GitHub PR #{pr_number} Updated. Triggering God-Mode Security Analysis...")
            
            # In a real environment, we would `git checkout` the PR branch here.
            # For the POC, we simulate the pipeline running on the vulnerable app.
            
            # NOTE: Aegis pipeline runs synchronously here for demonstration, 
            # in production this would be dispatched to a background Celery worker.
            target_file = "vuln_app.py"
            if os.path.exists(target_file):
                run_aegis_pipeline(target_file)
            else:
                print(f"[Aegis - CI/CD] Error: {target_file} not found in repository root.")
                
            return {"status": f"Aegis Pipeline Engaged for PR #{pr_number}"}
            
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
