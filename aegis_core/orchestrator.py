import os
import sys
import json
import shutil
import subprocess
from agent_red import generate_exploit
from agent_blue import generate_fix
from sandbox import run_exploit_against_target
from security_utils import validate_safe_path, SecurityUtilsError
from config import get_functional_test_command
from dotenv import load_dotenv
import time
from datetime import datetime

load_dotenv()

# Explicit Status Codes
STATUS_LLM_FAILURE = "LLM_FAILURE"
STATUS_SCHEMA_VALIDATION_FAILURE = "SCHEMA_VALIDATION_FAILURE"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_RATE_LIMIT = "RATE_LIMIT_EXHAUSTION"
STATUS_UNSAFE_PATH = "UNSAFE_PATH"
STATUS_EMPTY_PATCH = "EMPTY_PATCH"
STATUS_FAILED_FUNCTIONAL_TESTS = "FAILED_FUNCTIONAL_TESTS"
STATUS_PARTIALLY_VERIFIED = "SECURITY_VERIFIED_BUT_FUNCTIONALLY_UNVERIFIED"
STATUS_SECURED = "SECURED"
STATUS_DUPLICATE = "DUPLICATE_FINDING"
STATUS_NO_VULNERABILITY = "NO_VULNERABILITY"

def create_validation_exploit(original_exploit_path: str, original_target: str, new_target: str) -> str:
    validation_exploit_path = "generated_exploit_validation.py"
    try:
        with open(original_exploit_path, 'r') as f:
            exploit_code = f.read()
        original_basename = os.path.basename(original_target)
        new_basename = os.path.basename(new_target)
        modified_code = exploit_code.replace(original_basename, new_basename)
        with open(validation_exploit_path, 'w') as f:
            f.write(modified_code)
        return validation_exploit_path
    except Exception as e:
        print(f"[Aegis - Orchestrator] Warning: Could not create validation exploit: {e}")
        return original_exploit_path

def is_duplicate_finding(target_file: str, cwe_id: str) -> bool:
    findings_file = ".aegis_findings.json"
    if os.path.exists(findings_file):
        try:
            with open(findings_file, 'r') as f:
                findings = json.load(f)
        except:
            findings = {}
    else:
        findings = {}
        
    key = f"{target_file}:{cwe_id}"
    if key in findings:
        return True
    
    findings[key] = datetime.now().isoformat()
    with open(findings_file, 'w') as f:
        json.dump(findings, f)
    return False

def run_aegis_pipeline(target_file: str):
    print("==================================================")
    print("🛡️ WELCOME TO AEGIS: THE GOD-MODE AI APPSEC PLATFORM 🛡️")
    print("==================================================")
    
    cwd = os.getcwd()
    try:
        validate_safe_path(cwd, target_file)
    except SecurityUtilsError as e:
        print(f"❌ {STATUS_UNSAFE_PATH}: {e}")
        sys.exit(1)
        
    print(f"Targeting Codebase: {target_file}")
    
    temp_exploit_file = "generated_exploit.py"
    fixed_app_file = target_file.replace(".py", "_secure.py")

    max_red_retries = 3
    red_attempt = 0
    red_previous_error = None
    vulnerability_found = False
    
    while red_attempt < max_red_retries:
        red_attempt += 1
        print(f"\n--- PHASE 1: RED TEAM ATTACK (Attempt {red_attempt}/{max_red_retries}) ---")
        success, result = generate_exploit(target_file, temp_exploit_file, red_previous_error)
        
        if not success:
            print(f"❌ Red Agent failed. Reason: {result}")
            if result in [STATUS_TIMEOUT, STATUS_RATE_LIMIT, STATUS_SCHEMA_VALIDATION_FAILURE, STATUS_LLM_FAILURE]:
                # If these failures bubble up, we must abort cleanly without writing
                sys.exit(1)
            continue

        if is_duplicate_finding(target_file, result.get("cwe_id")):
            print(f"⚠️ {STATUS_DUPLICATE}: This vulnerability was already found and patched previously. Skipping.")
            sys.exit(0) # Not an error, just skip

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
        print(f"✅ {STATUS_NO_VULNERABILITY}: The application appears perfectly secure against all fuzzing attempts.")
        sys.exit(0)

    max_retries = 3
    attempt = 0
    previous_error = None
    
    while attempt < max_retries:
        attempt += 1
        print(f"\n--- PHASE 3: BLUE TEAM REMEDIATION (Attempt {attempt}/{max_retries}) ---")
        
        success, result = generate_fix(target_file, temp_exploit_file, fixed_app_file, previous_error)
        
        if not success:
            print(f"❌ Blue Agent failed. Reason: {result}")
            if result in [STATUS_TIMEOUT, STATUS_RATE_LIMIT, STATUS_SCHEMA_VALIDATION_FAILURE, STATUS_EMPTY_PATCH, STATUS_LLM_FAILURE]:
                sys.exit(1)
            continue

        print(f"\n--- PHASE 4: VALIDATING THE FIX (Attempt {attempt}) ---")
        
        validation_exploit = create_validation_exploit(temp_exploit_file, target_file, fixed_app_file)
        still_vulnerable, docker_out = run_exploit_against_target(validation_exploit, fixed_app_file)
        
        print("\n==================================================")
        if still_vulnerable:
            print("❌ FAIL: The refactored code (Blue Team) is STILL vulnerable to the attack.")
            if attempt < max_retries:
                previous_error = docker_out
            else:
                print("❌ FATAL: Aegis exhausted all attempts to fix the codebase.")
                sys.exit(1)
        else:
            print("✅ SUCCESS: The refactored code successfully blocked the zero-day exploit!")
            
            test_cmd = get_functional_test_command(cwd)
            
            if not test_cmd:
                print("⚠️ WARNING: No functional test command found (e.g., pytest, npm test).")
                print(f"✅ RESULT: {STATUS_PARTIALLY_VERIFIED}")
                final_status = STATUS_PARTIALLY_VERIFIED
            else:
                print(f"🧪 Running Functional Tests: {test_cmd}")
                
                backup_file = target_file + ".bak"
                shutil.copy(target_file, backup_file)
                shutil.copy(fixed_app_file, target_file)
                
                try:
                    test_result = subprocess.run(
                        test_cmd, shell=True, capture_output=True, text=True, cwd=cwd
                    )
                    
                    if test_result.returncode == 0:
                        print("✅ SUCCESS: Functional tests passed! Patch is secure and functional.")
                        print(f"✅ RESULT: {STATUS_SECURED}")
                        final_status = STATUS_SECURED
                    else:
                        print(f"❌ {STATUS_FAILED_FUNCTIONAL_TESTS}: Functional tests FAILED after applying patch.")
                        if attempt < max_retries:
                            previous_error = f"Your patch blocked the exploit, but BROKE the functional tests.\nTest Error Output:\n{test_result.stdout}\n{test_result.stderr}\nYou must fix the vulnerability WITHOUT breaking the existing tests!"
                            shutil.copy(backup_file, target_file)
                            os.remove(backup_file)
                            continue
                        else:
                            print("❌ FATAL: Aegis exhausted all attempts to fix the codebase without breaking tests.")
                            shutil.copy(backup_file, target_file)
                            os.remove(backup_file)
                            sys.exit(1)
                finally:
                    if os.path.exists(backup_file):
                        shutil.copy(backup_file, target_file)
                        os.remove(backup_file)
            
            print(f"✅ The secure refactored code has been saved to: {fixed_app_file}")
            
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
                    "patched_code": fix_code,
                    "status": final_status
                }
                with open(report_path, 'w') as f:
                    json.dump(report, f, indent=2)
                print(f"[Aegis] 📊 Report saved to {report_path}")
            except Exception as e:
                print(f"[Aegis] Failed to save report: {e}")
                
            break
            
    # If the loop exhausted without finding a successful fix (rare because of sys.exit(1), but just in case)
    if attempt >= max_retries and 'final_status' not in locals():
        sys.exit(1)


if __name__ == "__main__":
    if not any([os.environ.get(k) for k in ["OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"]]):
        print("⚠️  WARNING: You don't seem to have an API key set in your environment.")
        print("Aegis requires an LLM to run. Please set GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY before running.")
    
    app_to_test = "vuln_app.py" if len(sys.argv) < 2 else sys.argv[1]
    
    if not os.path.exists(app_to_test):
        print(f"Error: Target file {app_to_test} not found.")
        sys.exit(1)
        
    run_aegis_pipeline(app_to_test)
