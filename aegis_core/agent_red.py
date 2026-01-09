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

    enterprise_context = load_codebase_context(target_code_path=target_code_path)

    prompt = f"""You are an elite offensive security researcher (Red Team).
    Analyze the following Python application and identify any critical vulnerabilities.

    RULES:
    1. The exploit MUST read the target from TARGET_APP environment variable.
    2. The exploit MUST use subprocess to execute the target application.
    3. The exploit MUST exit with code 0 if successful, code 1 if it fails.

    --- TARGET APP CODE ---
    {target_code}
    """

    try:
        model = os.environ.get("AEGIS_MODEL", "gemini/gemini-1.5-pro")
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
        print(f"[Aegis - Red Team Agent] 🕵️ Vulnerability Found: {data.get('cwe_id')} - {data.get('cve_type')} ({data.get('severity')})")
        exploit_code = data.get('exploit_code', '').strip()
        with open(output_exploit_path, 'w') as f:
            f.write(exploit_code)
        print(f"[Aegis - Red Team Agent] 🎯 Structured exploit generated.")
        return True
    except Exception as e:
        print(f"[Aegis - Red Team Agent] Error: {e}")
        return False
