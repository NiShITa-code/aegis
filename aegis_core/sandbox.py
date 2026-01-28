import subprocess
import os
from typing import Tuple

def run_exploit_against_target(exploit_path: str, target_app_path: str) -> Tuple[bool, str]:
    """Executes the exploit script inside an ephemeral Docker container."""
    print(f"\n[Aegis - Sandbox Judge] 🐳 Spinning up secure Docker container...")

    cwd = os.path.abspath(os.getcwd())
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{cwd}:/app",
        "-w", "/app",
        "-e", f"TARGET_APP={os.path.basename(target_app_path)}",
        "python:3.10-slim",
        "python", os.path.basename(exploit_path)
    ]

    try:
        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=30)
        print("Docker Sandbox Output:")
        print("-------------")
        print(result.stdout.strip())
        print(result.stderr.strip())
        print("-------------")
        if result.returncode == 0:
            print("[Aegis - Sandbox Judge] 🔴 VULNERABILITY CONFIRMED.")
            return True, result.stdout + "\n" + result.stderr
        else:
            print("[Aegis - Sandbox Judge] 🟢 SECURE: Exploit failed.")
            return False, result.stdout + "\n" + result.stderr
    except Exception as e:
        print(f"[Aegis - Sandbox Judge] Error: {e}")
        return False, str(e)
