from fastapi import FastAPI, Request, BackgroundTasks, Header, HTTPException, Security, Depends
import uvicorn
import os
import tempfile
import shutil
import subprocess
import hmac
import hashlib
import time
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from fastapi.responses import PlainTextResponse
import json
import glob
import uuid

# Local imports
from sast_scanner import run_semgrep, SASTFailedError
from github_utils import clone_pr_branch, post_pr_comment, apply_patch, get_pr_changed_files
from repository_scanner import RepositoryScanner
from reporter import AegisReporter, OrchestratorArtifact
from pydantic import ValidationError
from idempotency import store
from app_config import settings
from logger import log, current_scan_id

app = FastAPI(title="Aegis AI Webhook Server")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Concurrency & Rate Limiting
worker_semaphore = asyncio.Semaphore(settings.max_concurrent_workers)
rate_limit_store = defaultdict(list)

def check_rate_limit(repo: str) -> bool:
    now = datetime.now()
    cutoff = now - timedelta(hours=1)
    rate_limit_store[repo] = [t for t in rate_limit_store[repo] if t > cutoff]
    if len(rate_limit_store[repo]) >= settings.max_requests_per_repo_per_hour:
        return False
    rate_limit_store[repo].append(now)
    return True

# Authentication Dependency
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

def get_tenant_config(auth_header: str = Security(api_key_header)):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing or invalid token")
        
    token = auth_header.replace("Bearer ", "")
    
    tenant_match = None
    for tenant, config in settings.tenant_config.items():
        if hmac.compare_digest(token, config.api_key.get_secret_value()):
            tenant_match = config
            break
            
    if not tenant_match:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    return tenant_match

def can_access_repo(tenant_config, repo: str) -> bool:
    # Wildcard tenants (e.g. test/internal) can see all repos
    if "*" in tenant_config.repos:
        return True
    if not repo:
        return False
    return repo in tenant_config.repos

@app.get("/api/reports")
def get_reports(limit: int = 50, tenant=Depends(get_tenant_config)):
    if settings.is_production() and not settings.tenant_config:
        raise HTTPException(status_code=403, detail="Reports API disabled: tenant config missing.")
        
    reports_dir = settings.reports_dir
    if not os.path.exists(reports_dir):
        return {"reports": []}
        
    reports = []
    for filepath in glob.glob(os.path.join(reports_dir, "*.json")):
        try:
            with open(filepath, 'r') as f:
                data = json.loads(f.read())
                repo_name = data.get("repo_metadata", {}).get("repo", "")
                if can_access_repo(tenant, repo_name):
                    reports.append(data)
        except Exception:
            pass
    reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"reports": reports[:limit]}

@app.get("/api/reports/{scan_id}")
def get_single_report(scan_id: str, tenant=Depends(get_tenant_config)):
    reports_dir = settings.reports_dir
    filepath = os.path.join(reports_dir, f"{scan_id}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                data = json.loads(f.read())
                repo_name = data.get("repo_metadata", {}).get("repo", "")
                if not can_access_repo(tenant, repo_name):
                    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Unauthorized for this repository")
                return data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read report: {e}")
    raise HTTPException(status_code=404, detail="Report not found")

@app.get("/api/reports/{scan_id}/markdown", response_class=PlainTextResponse)
def get_single_report_markdown(scan_id: str, tenant=Depends(get_tenant_config)):
    # First verify access using the JSON metadata
    get_single_report(scan_id, tenant)
    
    reports_dir = settings.reports_dir
    filepath = os.path.join(reports_dir, f"{scan_id}.md")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return f.read()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read report: {e}")
    raise HTTPException(status_code=404, detail="Markdown Report not found")

async def process_pr_with_timeout(repo_full_name: str, pr_number: int):
    # Enforce concurrency limit
    async with worker_semaphore:
        try:
            # Enforce timeout
            await asyncio.wait_for(
                asyncio.to_thread(process_pr_sync, repo_full_name, pr_number),
                timeout=settings.worker_timeout_seconds
            )
        except asyncio.TimeoutError:
            log.error(f"Worker timeout exceeded for PR #{pr_number} in {repo_full_name}")

def process_pr_sync(repo_full_name: str, pr_number: int):
    scan_id = f"scan_{uuid.uuid4().hex[:8]}_{pr_number}"
    current_scan_id.set(scan_id)
    
    reporter = AegisReporter(scan_id)
    reporter.reports_dir = settings.reports_dir
    reporter.repo_metadata = {"repo": repo_full_name, "pr": pr_number}
    
    log.info(f"Starting async pipeline for PR #{pr_number} in {repo_full_name}")
    
    temp_dir = tempfile.mkdtemp(prefix="aegis_")
    intermediate_dir = os.path.join(settings.reports_dir, "intermediate", scan_id)
    os.makedirs(intermediate_dir, exist_ok=True)
    
    try:
        success = clone_pr_branch(repo_full_name, pr_number, temp_dir)
        if not success:
            log.error("Failed to clone PR branch.")
            reporter.sast_summary["failed"] = True
            return

        changed_files = get_pr_changed_files(repo_full_name, pr_number)
        scanner = RepositoryScanner(temp_dir)
        targets = scanner.get_scan_targets(changed_files)
        
        reporter.scan_targets = targets
        reporter.skipped_files = scanner.skipped_files if hasattr(scanner, 'skipped_files') else {}
        
        if not targets:
            log.info("No relevant scan targets identified. Pipeline stopping.")
            post_pr_comment(repo_full_name, pr_number, "🛡️ **Aegis God-Mode Analysis:** No actionable files modified in this PR. Skipping scan.")
            return

        try:
            vulnerable_files = run_semgrep(targets)
        except SASTFailedError as e:
            log.error(f"SAST_FAILED: {e}")
            post_pr_comment(repo_full_name, pr_number, f"⚠️ **Aegis God-Mode Analysis:** SAST pre-filter failed (Status: `SAST_FAILED`). For safety, Aegis has aborted the scan rather than blindly analyzing the repository.\n\nError: {e}")
            reporter.sast_summary["failed"] = True
            return
            
        reporter.sast_summary["vulnerable_files_count"] = len(vulnerable_files)
            
        if not vulnerable_files:
            log.info("No potential vulnerabilities found by SAST. Aegis pipeline stopping.")
            post_pr_comment(repo_full_name, pr_number, "🛡️ **Aegis God-Mode Analysis:** No vulnerabilities detected during SAST pre-scan. Code appears secure.")
            return

        budgets = scanner.budgets
        max_vulns = budgets.get("max_vulnerabilities", 5)
        if len(vulnerable_files) > max_vulns:
            log.warning(f"Semgrep found {len(vulnerable_files)} vulnerable files, exceeding budget ({max_vulns}). Truncating.")
            vulnerable_files = list(vulnerable_files)[:max_vulns]

        fixed_files = []
        
        for idx, target_file in enumerate(vulnerable_files):
            log.info(f"Engaging God-Mode on flagged file: {target_file}")
            try:
                orchestrator_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "orchestrator.py"))
                output_json_path = os.path.join(intermediate_dir, f"target_{idx}.json")
                
                result = subprocess.run(
                    ["python", orchestrator_path, target_file, "--output-json", output_json_path],
                    capture_output=True,
                    text=True
                )
                
                if result.stdout:
                    log.info(f"Orchestrator Output for {os.path.basename(target_file)}:\n{result.stdout}")
                if result.stderr:
                    log.error(f"Orchestrator Error:\n{result.stderr}")
                    
                if os.path.exists(output_json_path):
                    try:
                        with open(output_json_path, 'r') as f:
                            data = json.loads(f.read())
                        artifact = OrchestratorArtifact(**data)
                        reporter.add_orchestrator_artifact(artifact)
                    except (json.JSONDecodeError, ValidationError) as e:
                        log.error(f"Corrupted intermediate artifact for {target_file}: {e}")
                        reporter.add_orchestrator_artifact(OrchestratorArtifact(
                            target_file=os.path.basename(target_file),
                            status="CORRUPTED_ARTIFACT",
                            sandbox_output=f"Artifact corruption: {e}",
                            original_code="", exploit_code="", patched_code=""
                        ))
                
                if result.returncode == 0:
                    secure_file_path = target_file.replace(".py", "_secure.py")
                    if os.path.exists(secure_file_path):
                        shutil.copy(secure_file_path, target_file)
                        rel_file_path = os.path.relpath(target_file, temp_dir)
                        fixed_files.append(rel_file_path)
                else:
                    log.warning(f"Orchestrator failed to secure {target_file}. Skipping commit.")
                    
            except Exception as e:
                log.error(f"Error running orchestrator on {target_file}: {e}")

        if fixed_files:
            success = apply_patch(temp_dir, fixed_files, "🛡️ Aegis God-Mode: Secured vulnerabilities", repo_full_name, pr_number)
            if not success:
                log.error("Failed to push or create PR for the patch.")
                reporter.github_write_action = "FAILED"
            else:
                reporter.github_write_action = "PUSHED_OR_PR_CREATED"
        else:
            post_pr_comment(
                repo_full_name, 
                pr_number, 
                "🛡️ **Aegis God-Mode Analysis:** Vulnerabilities flagged by SAST could not be verified by the Sandbox. No fixes required."
            )
            reporter.github_write_action = "COMMENTED"

    except Exception as e:
        log.exception(f"Unhandled exception in pipeline: {e}")
        reporter.final_status = "FATAL_ERROR"
    finally:
        # Save partial or final report
        reporter.save()
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(intermediate_dir, ignore_errors=True)

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
                
            if not check_rate_limit(repo_full_name):
                log.warning(f"Rate limit exceeded for {repo_full_name}")
                return {"status": "Error: Rate limit exceeded."}
                
            log.info(f"🚨 GitHub PR #{pr_number} Updated. Queuing Async Analysis...")
            
            if x_github_delivery:
                store.mark_processed(x_github_delivery)
            
            background_tasks.add_task(process_pr_with_timeout, repo_full_name, pr_number)
                
            return {"status": f"Aegis Pipeline Queued for PR #{pr_number}"}
            
        return {"status": "Ignored - Event not actionable."}
    except Exception as e:
        log.error(f"Webhook Error: {e}")
        return {"error": str(e)}

@app.get("/health")
def health_check():
    return {"status": "Aegis God-Mode is actively listening for commits."}

@app.get("/readiness")
def readiness_check():
    if settings.is_production():
        if not settings.github_app_id or not settings.github_app_private_key:
            raise HTTPException(status_code=503, detail="Not Ready: Missing GitHub App Credentials in production.")
        if not settings.tenant_config:
            raise HTTPException(status_code=503, detail="Not Ready: Missing Tenant Config in production.")
    return {"status": "Ready", "env": settings.aegis_env}

@app.post("/api/cleanup")
def trigger_cleanup(background_tasks: BackgroundTasks):
    background_tasks.add_task(cleanup_old_reports)
    return {"status": "Cleanup queued"}

def cleanup_old_reports():
    reports_dir = settings.reports_dir
    if not os.path.exists(reports_dir):
        return
        
    cutoff = time.time() - (settings.report_retention_days * 86400)
    for filepath in glob.glob(os.path.join(reports_dir, "*.*")):
        try:
            if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
                log.info(f"Deleted old report: {filepath}")
        except Exception as e:
            log.error(f"Error deleting {filepath}: {e}")

if __name__ == "__main__":
    log.info("🛡️ AEGIS GITHUB WEBHOOK LISTENER STARTING...")
    log.info("Listening on http://0.0.0.0:8000/github-webhook")
    uvicorn.run(app, host="0.0.0.0", port=8000)
