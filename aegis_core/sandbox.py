import subprocess
import os

from typing import Tuple

def run_exploit_against_target(exploit_path: str, target_app_path: str) -> Tuple[bool, str]:
    """
    Executes the exploit script safely inside an ephemeral Docker container.
    Returns True if the exploit succeeded (vulnerability exists), False otherwise.
    """
    print(f"\n[Aegis - Sandbox Judge] 🐳 Spinning up secure Docker container to run exploit...")
    
    # We must use absolute paths for Docker volume mounting
    cwd = os.path.abspath(os.getcwd())
    
    # Dynamic Docker Image Routing
    ext = os.path.splitext(target_app_path)[1].lower()
    if ext in ['.js', '.ts']:
        docker_image = "nikolaik/python-nodejs:python3.10-nodejs20"
    else:
        docker_image = "python:3.10-slim"
        
    docker_cmd = [
        "docker", "run", "--rm",
        "--network", "none", # Total network isolation for safety
        "-v", f"{cwd}:/app",
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
        print("[Aegis - Sandbox Judge] Falling back to INSECURE local execution...")
        # Fallback for systems without docker 
        return run_exploit_local_fallback(exploit_path, target_app_path)
    except Exception as e:
        print(f"[Aegis - Sandbox Judge] Error running Docker sandbox: {e}")
        return False, str(e)

def run_exploit_local_fallback(exploit_path: str, target_app_path: str) -> Tuple[bool, str]:
    """Fallback if docker isn't installed. Unsafe!"""
    env = os.environ.copy()
    env["TARGET_APP"] = target_app_path
    try:
        result = subprocess.run(["python", exploit_path], env=env, capture_output=True, text=True, timeout=10)
        return result.returncode == 0, result.stdout.strip() + "\n" + result.stderr.strip()
    except Exception as e:
        return False, str(e)
