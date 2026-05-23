import os
import sys
import re
from agent_red import generate_exploit
from agent_blue import generate_fix
from sandbox import run_exploit_against_target
from dotenv import load_dotenv

load_dotenv()

def create_validation_exploit(original_exploit_path: str, original_target: str, new_target: str) -> str:
    """
    Creates a modified copy of the exploit that targets the fixed file instead
    of the original vulnerable file. This is the KEY to making validation work.
    """
    validation_exploit_path = "generated_exploit_validation.py"
    try:
        with open(original_exploit_path, 'r') as f:
            exploit_code = f.read()
        
        # Replace all references to the original target with the new target
        original_basename = os.path.basename(original_target)
        new_basename = os.path.basename(new_target)
        modified_code = exploit_code.replace(original_basename, new_basename)
        
        # Write the modified exploit script
        with open(validation_exploit_path, 'w') as f:
            f.write(modified_code)
        
        return validation_exploit_path
    except Exception as e:
        print(f"[Aegis - Orchestrator] Warning: Could not create validation exploit: {e}")
        return original_exploit_path

def run_aegis_pipeline(target_file: str):
    print("==================================================")
    print("🛡️ WELCOME TO AEGIS: THE GOD-MODE AI APPSEC PLATFORM 🛡️")
    print("==================================================")
    print(f"Targeting Codebase: {target_file}")
    
    # Files generated during the pipeline
    temp_exploit_file = "generated_exploit.py"
    fixed_app_file = target_file.replace(".py", "_secure.py")

    # STEP 1 & 2: Attack Generation (Red Team) and Verification
    max_red_retries = 3
    red_attempt = 0
    red_previous_error = None
    vulnerability_found = False
    
    while red_attempt < max_red_retries:
        red_attempt += 1
        print(f"\n--- PHASE 1: RED TEAM ATTACK (Attempt {red_attempt}/{max_red_retries}) ---")
        success = generate_exploit(target_file, temp_exploit_file, red_previous_error)
        
        if not success or not os.path.exists(temp_exploit_file):
            print("❌ Red Agent failed to generate an exploit structure. Exiting.")
            sys.exit(1)

        print("\n--- PHASE 2: EXPLOIT VERIFICATION ---")
        is_vulnerable, docker_out = run_exploit_against_target(temp_exploit_file, target_file)
        
        if is_vulnerable:
            vulnerability_found = True
            docker_out_proof = docker_out
            break
        else:
            print("❌ Exploit Failed or Sandbox Crashed. Feeding error back to Red Team for Fuzzing...")
            red_previous_error = docker_out

    if not vulnerability_found:
        print("✅ The application appears perfectly secure against all fuzzing attempts. No fixing required.")
        sys.exit(0)

    # STEP 3 & 4: Auto-Remediation (Blue Team) and Validation
    max_retries = 3
    attempt = 0
    previous_error = None
    
    while attempt < max_retries:
        attempt += 1
        print(f"\n--- PHASE 3: BLUE TEAM REMEDIATION (Attempt {attempt}/{max_retries}) ---")
        
        success = generate_fix(target_file, temp_exploit_file, fixed_app_file, previous_error)
        
        if not success or not os.path.exists(fixed_app_file):
            print("❌ Blue Agent failed to generate a fix structure. Exiting.")
            sys.exit(1)

        print(f"\n--- PHASE 4: VALIDATING THE FIX (Attempt {attempt}) ---")
        
        # CRITICAL: Rewrite the exploit to target the fixed file, not the original
        validation_exploit = create_validation_exploit(temp_exploit_file, target_file, fixed_app_file)
        still_vulnerable, docker_out = run_exploit_against_target(validation_exploit, fixed_app_file)
        
        print("\n==================================================")
        if still_vulnerable:
            print("❌ FAIL: The refactored code (Blue Team) is STILL vulnerable to the attack.")
            if attempt < max_retries:
                print("Looping back to Phase 3 for self-healing...")
                previous_error = docker_out
            else:
                print("❌ FATAL: Aegis exhausted all attempts to fix the codebase.")
                sys.exit(1)
        else:
            print("✅ SUCCESS: The refactored code successfully blocked the zero-day exploit!")
            print(f"✅ The secure refactored code has been saved to: {fixed_app_file}")
            print("==================================================")
            
            # Phase 3: Save Report for the Proof Dashboard
            import json
            import time
            from datetime import datetime
            
            os.makedirs(".aegis_reports", exist_ok=True)
            report_id = f"report_{int(time.time())}"
            report_path = os.path.join(".aegis_reports", f"{report_id}.json")
            
            try:
                with open(target_file, 'r') as f: orig_code = f.read()
                with open(temp_exploit_file, 'r') as f: exp_code = f.read()
                with open(fixed_app_file, 'r') as f: fix_code = f.read()
                
                report = {
                    "id": report_id,
                    "timestamp": datetime.now().isoformat(),
                    "target_file": os.path.basename(target_file),
                    "original_code": orig_code,
                    "exploit_code": exp_code,
                    "sandbox_output": docker_out_proof,
                    "patched_code": fix_code
                }
                with open(report_path, 'w') as f:
                    json.dump(report, f, indent=2)
                print(f"[Aegis] 📊 Report saved to {report_path}")
            except Exception as e:
                print(f"[Aegis] Failed to save report: {e}")
                
            break


if __name__ == "__main__":
    if not any([os.environ.get(k) for k in ["OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"]]):
        print("⚠️  WARNING: You don't seem to have an API key set in your environment.")
        print("Aegis requires an LLM to run. Please set GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY before running.")
    
    # Defaulting to testing the vuln_app
    app_to_test = "vuln_app.py" if len(sys.argv) < 2 else sys.argv[1]
    
    if not os.path.exists(app_to_test):
        print(f"Error: Target file {app_to_test} not found.")
        sys.exit(1)
        
    run_aegis_pipeline(app_to_test)
