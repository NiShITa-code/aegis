import os
import sys
import json
import shutil
import subprocess
from agent_red import generate_exploit
from agent_blue import generate_fix
from sandbox import run_exploit_against_target
from security_utils import validate_safe_path, SecurityUtilsError
from config import get_functional_test_command, get_aegis_budgets
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
STATUS_SCAN_TOO_LARGE = "SCAN_TOO_LARGE"
STATUS_SAST_FAILED = "SAST_FAILED"
STATUS_NO_RELEVANT_CONTEXT = "NO_RELEVANT_CONTEXT"

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
    start_time = time.time()
    print("==================================================")
    print("🛡️ WELCOME TO AEGIS: THE GOD-MODE AI APPSEC PLATFORM 🛡️")
    print("==================================================")
    
    cwd = os.getcwd()
    try:
        validate_safe_path(cwd, target_file)
    except SecurityUtilsError as e:
        print(f"❌ {STATUS_UNSAFE_PATH}: {e}")
        sys.exit(1)
        
    budgets = get_aegis_budgets(cwd)
    if os.path.exists(target_file) and os.path.getsize(target_file) > budgets.get("max_file_bytes", 500 * 1024):
        print(f"❌ {STATUS_SCAN_TOO_LARGE}: Target file {target_file} exceeds max file size budget.")
        sys.exit(1)

        
    print(f"Targeting Codebase: {target_file}")
    
    temp_exploit_file = "generated_exploit.py"
    fixed_app_file = target_file.replace(".py", "_secure.py")

    max_red_retries = 3
    red_attempt = 0
    red_previous_error = None
    vulnerability_found = False
    
    max_llm_calls = budgets.get("max_llm_calls", 20)
    current_llm_calls = 0
    
    while red_attempt < max_red_retries:
        red_attempt += 1
        current_llm_calls += 1
        if current_llm_calls > max_llm_calls:
            print(f"❌ {STATUS_RATE_LIMIT}: Max LLM calls budget exhausted.")
            sys.exit(1)
            
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
        current_llm_calls += 1
        if current_llm_calls > max_llm_calls:
            print(f"❌ {STATUS_RATE_LIMIT}: Max LLM calls budget exhausted.")
            sys.exit(1)
            
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
                break
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
                            break
                finally:
                    if os.path.exists(backup_file):
                        shutil.copy(backup_file, target_file)
                        os.remove(backup_file)
            
            # Always generate an orchestrator artifact
            artifact = {
                "target_file": os.path.basename(target_file),
                "status": final_status,
                "sandbox_output": docker_out_proof,
                "original_code": orig_code,
                "exploit_code": exp_code,
                "patched_code": fix_code,
                "functional_test_result": "PASSED" if final_status == STATUS_SECURED else ("FAILED" if final_status == STATUS_FAILED_FUNCTIONAL_TESTS else "NONE"),
                "llm_calls": current_llm_calls,
                "token_usage": getattr(sys.modules.get('llm_utils'), 'LLM_TELEMETRY', {}),
                "duration_seconds": time.time() - start_time
            }
            
            output_json_path = os.environ.get("AEGIS_ORCHESTRATOR_OUTPUT_JSON")
            if output_json_path:
                # Atomic write
                tmp_path = output_json_path + ".tmp"
                with open(tmp_path, 'w') as f:
                    json.dump(artifact, f, indent=2)
                os.replace(tmp_path, output_json_path)
            
            print(f"✅ The secure refactored code has been saved to: {fixed_app_file}")
            break
            
    # If the loop exhausted without finding a successful fix
    if attempt >= max_retries and 'final_status' not in locals():
        output_json_path = os.environ.get("AEGIS_ORCHESTRATOR_OUTPUT_JSON")
        if output_json_path:
            artifact = {
                "target_file": os.path.basename(target_file),
                "status": previous_error_status if 'previous_error_status' in locals() else STATUS_LLM_FAILURE,
                "sandbox_output": previous_error if previous_error else "",
                "original_code": "", "exploit_code": "", "patched_code": "",
                "functional_test_result": "NONE",
                "llm_calls": current_llm_calls,
                "token_usage": getattr(sys.modules.get('llm_utils'), 'LLM_TELEMETRY', {}),
                "duration_seconds": time.time() - start_time
            }
            tmp_path = output_json_path + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(artifact, f, indent=2)
            os.replace(tmp_path, output_json_path)
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("target_file", help="The python file to scan")
    parser.add_argument("--output-json", help="Path to write the intermediate artifact JSON")
    args = parser.parse_args()
    
    if args.output_json:
        os.environ["AEGIS_ORCHESTRATOR_OUTPUT_JSON"] = args.output_json
        
    if not any([os.environ.get(k) for k in ["OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"]]):
        print("⚠️  WARNING: You don't seem to have an API key set in your environment.")
        print("Aegis requires an LLM to run. Please set GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY before running.")
    
    if not os.path.exists(args.target_file):
        print(f"Error: Target file {args.target_file} not found.")
        sys.exit(1)
        
    run_aegis_pipeline(args.target_file)
