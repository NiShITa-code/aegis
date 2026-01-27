import os
import json
import re
from litellm import completion
from pydantic import BaseModel, Field
from context_loader import load_codebase_context

class ExploitPayload(BaseModel):
    cve_type: str = Field(description="The type of vulnerability found (e.g. SQL Injection, Command Injection)")
    cwe_id: str = Field(description="The MITRE CWE ID (e.g. CWE-89, CWE-79)")
    severity: str = Field(description="Severity (CRITICAL, HIGH, MEDIUM, LOW)")
    exploit_code: str = Field(description="The raw Python code to run the exploit.")

def extract_json_from_text(raw_text: str) -> dict:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r'```(?:json)?\n(.*?)\n```', raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        start = raw_text.find('{')
        end = raw_text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(raw_text[start:end+1])
            except:
                pass
    raise ValueError("Could not extract valid JSON from LLM response.")

def generate_exploit(target_code_path: str, output_exploit_path: str, previous_error: str = None) -> bool:
    """Reads target code and uses an LLM with Structured Outputs to generate an exploit script."""
    print("[Aegis - Red Team Agent] Analyzing target code strictly...")
    
    try:
        with open(target_code_path, 'r') as f:
            target_code = f.read()
    except Exception as e:
        print(f"[Aegis - Red Team Agent] Could not read target code: {e}")
        return False

    # Load the entire architectural context
    enterprise_context = load_codebase_context(target_code_path=target_code_path)

    prompt = f"""You are an elite offensive security researcher (Red Team).
    Analyze the following Python application within the context of the entire enterprise architecture,
    and identify any critical vulnerabilities.
    
    RULES:
    1. The exploit script MUST read the target filename from the TARGET_APP environment variable: `target = os.environ.get("TARGET_APP", "vuln_app.py")`
    2. The exploit script MUST execute the target application using `subprocess` and pass the malicious payload as arguments.
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

    try:
        model = os.environ.get("AEGIS_MODEL", "gemini/gemini-1.5-pro")
        
        for attempt in range(2):
            try:
                response = completion(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a cybersecurity tool that outputs ONLY valid JSON matching the schema."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format=ExploitPayload
                )
                
                raw_json = response.choices[0].message.content
                data = extract_json_from_text(raw_json)
                break
            except Exception as parse_e:
                if attempt == 1:
                    raise parse_e
                print("[Aegis - Red Team Agent] JSON parse failed. Retrying...")
                
        print(f"[Aegis - Red Team Agent] 🕵️ Vulnerability Found: {data.get('cwe_id')} - {data.get('cve_type')} ({data.get('severity')})")
        
        exploit_code = data.get('exploit_code', '').strip()
            
        with open(output_exploit_path, 'w') as f:
            f.write(exploit_code)
            
        print(f"[Aegis - Red Team Agent] 🎯 Structured exploit generated and saved to {output_exploit_path}.")
        return True
    except Exception as e:
        print(f"[Aegis - Red Team Agent] Error generating exploit. Ensure API keys are set. Error: {e}")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python agent_red.py <target_app.py> <output_exploit.py>")
    else:
        generate_exploit(sys.argv[1], sys.argv[2])
