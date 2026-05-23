import subprocess
import os
import shutil
import tempfile
from typing import Tuple

def run_exploit_against_target(exploit_path: str, target_app_path: str) -> Tuple[bool, str]:
    """
    Executes the exploit script safely inside an ephemeral Docker container.
    Returns True if the exploit succeeded (vulnerability exists), False otherwise.
    """
    print(f"\n[Aegis - Sandbox Judge] 🐳 Spinning up secure Docker container to run exploit...")
    
    # Create isolated per-scan temp workspace
    temp_workspace = tempfile.mkdtemp(prefix="aegis_sandbox_")
    
    # Copy only necessary files
    safe_target_path = os.path.join(temp_workspace, os.path.basename(target_app_path))
    safe_exploit_path = os.path.join(temp_workspace, os.path.basename(exploit_path))
    
    try:
        shutil.copy2(target_app_path, safe_target_path)
        shutil.copy2(exploit_path, safe_exploit_path)
    except Exception as e:
        shutil.rmtree(temp_workspace, ignore_errors=True)
        return False, f"Failed to setup sandbox workspace: {e}"
    
    # Dynamic Docker Image Routing
    ext = os.path.splitext(target_app_path)[1].lower()
    if ext in ['.js', '.ts']:
        docker_image = "nikolaik/python-nodejs:python3.10-nodejs20"
    elif ext == '.go':
        docker_image = "golang:1.21-bullseye"
    else:
        docker_image = "python:3.10-slim"
        
    docker_cmd = [
        "docker", "run", "--rm",
        "--network", "none", # Total network isolation for safety
        "--memory=512m",     # Resource limits
        "--cpus=1.0",
        "--pids-limit=50",
        "-v", f"{temp_workspace}:/app", # Mount ONLY the temp workspace
        "-w", "/app",
        "-e", f"TARGET_APP={os.path.basename(target_app_path)}",
        docker_image,
        "python", os.path.basename(exploit_path)
    ]
    
    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=30 # Increased hard timeout for web servers
        )
        
        print("Docker Sandbox Output:")
        print("-------------")
        print(result.stdout.strip())
        print(result.stderr.strip())
        print("-------------")
        
        if result.returncode != 0 and ("error during connect" in result.stderr or "Cannot connect to the Docker daemon" in result.stderr):
            print("[Aegis - Sandbox Judge] ⚠️ WARNING: Docker daemon is not running!")
            print("[Aegis - Sandbox Judge] FATAL: Secure Sandbox Unavailable. Aborting to prevent host execution.")
            return False, "Docker daemon unavailable."
            
        if result.returncode == 0:
            print("[Aegis - Sandbox Judge] 🔴 VULNERABILITY CONFIRMED: The exploit was successful in Docker.")
            return True, result.stdout.strip() + "\n" + result.stderr.strip()
        else:
            print("[Aegis - Sandbox Judge] 🟢 SECURE: The exploit failed or was blocked by the sandbox.")
            return False, result.stdout.strip() + "\n" + result.stderr.strip()
            
    except subprocess.TimeoutExpired:
        print("[Aegis - Sandbox Judge] 🟢 SECURE: Exploit timed out (likely infinite loop blocked).")
        return False, "Execution timed out."
    except FileNotFoundError:
        print("[Aegis - Sandbox Judge] ⚠️ WARNING: Docker is not installed or not running on this machine!")
        print("[Aegis - Sandbox Judge] FATAL: Secure Sandbox Unavailable. Aborting to prevent host execution.")
        return False, "Docker not installed."
    except Exception as e:
        print(f"[Aegis - Sandbox Judge] Error running Docker sandbox: {e}")
        return False, str(e)
    finally:
        # Cleanup isolated workspace
        shutil.rmtree(temp_workspace, ignore_errors=True)
