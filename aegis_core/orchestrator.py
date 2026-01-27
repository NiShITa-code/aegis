import os
import sys
from agent_red import generate_exploit

def run_aegis_pipeline(target_file: str):
    print("==================================================")
    print("🛡️ WELCOME TO AEGIS: THE GOD-MODE AI APPSEC PLATFORM 🛡️")
    print("==================================================")
    print(f"Targeting Codebase: {target_file}")

    temp_exploit_file = "generated_exploit.py"

    # PHASE 1: Red Team Attack
    max_red_retries = 3
    red_attempt = 0
    red_previous_error = None

    while red_attempt < max_red_retries:
        red_attempt += 1
        print(f"\n--- PHASE 1: RED TEAM ATTACK (Attempt {red_attempt}/{max_red_retries}) ---")
        success = generate_exploit(target_file, temp_exploit_file, red_previous_error)
        if not success:
            print("❌ Red Agent failed to generate exploit. Exiting.")
            sys.exit(1)
        # TODO: Phase 2 Sandbox verification
        print("Sandbox verification not yet implemented.")
        break

if __name__ == "__main__":
    app_to_test = "vuln_app.py" if len(sys.argv) < 2 else sys.argv[1]
    if not os.path.exists(app_to_test):
        print(f"Error: Target file {app_to_test} not found.")
        sys.exit(1)
    run_aegis_pipeline(app_to_test)
