import os
import json
from litellm import completion

def generate_fix(target_code_path: str, exploit_path: str, output_fixed_path: str, previous_error: str = None) -> bool:
    """Reads vulnerable code and exploit, uses an LLM to generate secure code."""
    print("[Aegis - Blue Team Agent] Formulating a secure patch...")

    try:
        with open(target_code_path, 'r') as f:
            target_code = f.read()
        with open(exploit_path, 'r') as f:
            exploit_code = f.read()
    except Exception as e:
        print(f"[Aegis - Blue Team Agent] Could not read files: {e}")
        return False

    prompt = f"""You are an elite defensive security engineer (Blue Team).
    A Red Team agent has exploited the application. Refactor it to mitigate the vulnerability.

    --- ORIGINAL VULNERABLE CODE ---
    {target_code}

    --- RED TEAM EXPLOIT USED ---
    {exploit_code}

    Output only the secure Python code.
    """

    try:
        model = os.environ.get("AEGIS_MODEL", "gemini/gemini-1.5-pro")
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You are a cybersecurity tool. Output only secure Python code."},
                {"role": "user", "content": prompt}
            ]
        )
        safe_code = response.choices[0].message.content.strip()
        with open(output_fixed_path, 'w') as f:
            f.write(safe_code)
        print(f"[Aegis - Blue Team Agent] 🛡️ Secure refactoring complete!")
        return True
    except Exception as e:
        print(f"[Aegis - Blue Team Agent] Error: {e}")
        return False
