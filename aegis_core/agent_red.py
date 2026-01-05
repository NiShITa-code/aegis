import os
import json
from litellm import completion
from context_loader import load_codebase_context

def generate_exploit(target_code_path: str, output_exploit_path: str, previous_error: str = None) -> bool:
    """Reads target code and uses an LLM to generate an exploit script."""
    print("[Aegis - Red Team Agent] Analyzing target code...")

    try:
        with open(target_code_path, 'r') as f:
            target_code = f.read()
    except Exception as e:
        print(f"[Aegis - Red Team Agent] Could not read target code: {e}")
        return False

    enterprise_context = load_codebase_context(target_code_path=target_code_path)

    prompt = f"""You are an elite offensive security researcher.
    Analyze the following Python application and identify any critical vulnerabilities.
    Generate a working Python exploit script.

    --- TARGET APP CODE ---
    {target_code}
    """

    try:
        model = os.environ.get("AEGIS_MODEL", "gemini/gemini-1.5-pro")
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You are a cybersecurity tool. Output only the exploit Python script."},
                {"role": "user", "content": prompt}
            ]
        )
        exploit_code = response.choices[0].message.content.strip()
        with open(output_exploit_path, 'w') as f:
            f.write(exploit_code)
        print(f"[Aegis - Red Team Agent] Exploit generated and saved to {output_exploit_path}.")
        return True
    except Exception as e:
        print(f"[Aegis - Red Team Agent] Error: {e}")
        return False
