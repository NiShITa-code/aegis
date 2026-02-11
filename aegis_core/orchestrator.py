import os
import sys
from agent_red import generate_exploit
from sandbox import run_exploit_against_target

def run_aegis_pipeline(target_file: str):
    print("==================================================")
    print("🛡️ WELCOME TO AEGIS: THE GOD-MODE AI APPSEC PLATFORM 🛡️")
    print("==================================================")
    print(f"Targeting Codebase: {target_file}")

    temp_exploit_file = "generated_exploit.py"
    vulnerability_found = False
    max_red_retries = 3
    red_attempt = 0
    red_previous_error = None

    while red_attempt < max_red_retries:
        red_attempt += 1
        print(f"\n--- PHASE 1: RED TEAM ATTACK (Attempt {red_attempt}/{max_red_retries}) ---")
        success = generate_exploit(target_file, temp_exploit_file, red_previous_error)
        if not success:
            print("❌ Red Agent failed. Exiting.")
            sys.exit(1)

        print("\n--- PHASE 2: EXPLOIT VERIFICATION ---")
        is_vulnerable, docker_out = run_exploit_against_target(temp_exploit_file, target_file)

        if is_vulnerable:
            vulnerability_found = True
            break
        else:
            print("❌ Exploit Failed. Feeding error back to Red Team...")
            red_previous_error = docker_out

    if not vulnerability_found:
        print("✅ Application appears secure against all fuzzing attempts.")
        sys.exit(0)

    print("\n--- PHASE 3 & 4 coming soon (Blue Team Remediation) ---")

if __name__ == "__main__":
    app_to_test = "vuln_app.py" if len(sys.argv) < 2 else sys.argv[1]
    if not os.path.exists(app_to_test):
        print(f"Error: Target file {app_to_test} not found.")
        sys.exit(1)
    run_aegis_pipeline(app_to_test)
