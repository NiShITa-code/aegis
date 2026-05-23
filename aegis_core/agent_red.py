import os
from pydantic import BaseModel, Field
from context_loader import load_codebase_context
from llm_utils import safe_call_llm

class ExploitPayload(BaseModel):
    cve_type: str = Field(description="The type of vulnerability found (e.g. SQL Injection, Command Injection)")
    cwe_id: str = Field(description="The MITRE CWE ID (e.g. CWE-89, CWE-79)")
    severity: str = Field(description="Severity (CRITICAL, HIGH, MEDIUM, LOW)")
    exploit_code: str = Field(description="The raw Python code to run the exploit.")

def generate_exploit(target_code_path: str, output_exploit_path: str, previous_error: str = None):
    """
    Reads target code and uses an LLM with Structured Outputs to generate an exploit script.
    Returns (success_bool, status_code).
    """
    print("[Aegis - Red Team Agent] Analyzing target code strictly...")
    
    try:
        with open(target_code_path, 'r') as f:
            target_code = f.read()
    except Exception as e:
        print(f"[Aegis - Red Team Agent] Could not read target code: {e}")
        return False, "TARGET_READ_ERROR"

    enterprise_context = load_codebase_context(target_code_path=target_code_path)

    ext = os.path.splitext(target_code_path)[1].lower()
    if ext in ['.js', '.ts']:
        lang_name = "Node.js/JavaScript"
        run_cmd = "node"
    elif ext == '.go':
        lang_name = "Go"
        run_cmd = "go run"
    else:
        lang_name = "Python"
        run_cmd = "python"

    prompt = f"""You are an elite offensive security researcher (Red Team).
    Analyze the following {lang_name} application within the context of the entire enterprise architecture,
    and identify any critical vulnerabilities.
    
    RULES:
    1. The exploit script MUST read the target filename from the TARGET_APP environment variable: `target = os.environ.get("TARGET_APP", "{os.path.basename(target_code_path)}")`
    2. The exploit script MUST execute the target application using `subprocess` with the correct runtime (i.e. `subprocess.run(["{run_cmd}", target, ...])`) and pass the malicious payload as arguments.
    3. If the target application is a web server or API, your exploit script MUST start the server in a background thread, wait for it to initialize, and then execute HTTP requests against it to exploit the vulnerability.
    4. The exploit script MUST exit with code 0 if the exploit is SUCCESSFUL.
    5. The exploit script MUST exit with code 1 if the exploit FAILS.
    
    --- ENTIRE PROJECT ARCHITECTURE CONTEXT ---
    {enterprise_context}
    
    --- TARGET APP CODE TO EXPLOIT ---
    {target_code}
    """
    
    if previous_error:
        prompt += f"\n    --- FEEDBACK ON PREVIOUS EXPLOIT ---\n    Your previous exploit script crashed or failed to cleanly exploit the target. Docker Output:\n    {previous_error}\n    Rewrite your payload to fix the errors and try again.\n"

    messages = [
        {"role": "system", "content": "You are a cybersecurity tool that outputs ONLY valid JSON matching the schema."},
        {"role": "user", "content": prompt}
    ]

    data, status_code = safe_call_llm(messages, ExploitPayload)
    
    if status_code != "SUCCESS" or not data:
        print(f"[Aegis - Red Team Agent] Failed to generate exploit. Status: {status_code}")
        return False, status_code
        
    print(f"[Aegis - Red Team Agent] 🕵️ Vulnerability Found: {data.cwe_id} - {data.cve_type} ({data.severity})")
    
    exploit_code = data.exploit_code.strip()
    
    if not exploit_code:
        print("[Aegis - Red Team Agent] Error: Generated exploit code is empty.")
        return False, "EMPTY_PATCH"
        
    try:
        with open(output_exploit_path, 'w') as f:
            f.write(exploit_code)
    except Exception as e:
        print(f"[Aegis - Red Team Agent] Could not write exploit: {e}")
        return False, "WRITE_ERROR"
        
    print(f"[Aegis - Red Team Agent] 🎯 Structured exploit generated and saved to {output_exploit_path}.")
    
    # Return True, status_code, and findings metadata for deduplication
    metadata = {
        "cwe_id": data.cwe_id,
        "cve_type": data.cve_type
    }
    return True, metadata

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python agent_red.py <target_app.py> <output_exploit.py>")
    else:
        generate_exploit(sys.argv[1], sys.argv[2])
