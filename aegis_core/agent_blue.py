import os
import json
import re
from litellm import completion
from pydantic import BaseModel, Field

class RemediationPayload(BaseModel):
    confidence_score: int = Field(description="Confidence from 1-100 that this patch closes the vulnerability.")
    explanation: str = Field(description="A 1-sentence explanation of what was changed.")
    secure_code: str = Field(description="The raw, entirely refactored Python code.")

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

def generate_fix(target_code_path: str, exploit_path: str, output_fixed_path: str, previous_error: str = None) -> bool:
    """Reads vulnerable code and exploit, uses an LLM to generate secure code via Structured JSON."""
    print("[Aegis - Blue Team Agent] Formulating a secure patch with strict schema adherence...")

    try:
        with open(target_code_path, 'r') as f:
            target_code = f.read()
        with open(exploit_path, 'r') as f:
            exploit_code = f.read()
    except Exception as e:
        print(f"[Aegis - Blue Team Agent] Could not read files: {e}")
        return False

    prompt = f"""You are an elite defensive security engineer (Blue Team).
    Refactor the application to mitigate the confirmed vulnerability.

    --- ORIGINAL VULNERABLE CODE ---
    {target_code}

    --- RED TEAM EXPLOIT SCRIPT ---
    {exploit_code}
    """

    if previous_error:
        prompt += f"\n--- FEEDBACK: YOUR PREVIOUS PATCH FAILED ---\n{previous_error}\nFix the flaws and try again.\n"

    try:
        model = os.environ.get("AEGIS_MODEL", "gemini/gemini-1.5-pro")
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You are a cybersecurity tool that outputs ONLY valid JSON matching the schema."},
                {"role": "user", "content": prompt}
            ],
            response_format=RemediationPayload
        )
        raw_json = response.choices[0].message.content
        data = extract_json_from_text(raw_json)
        print(f"[Aegis - Blue Team Agent] 🛠️ Fix Plan: {data.get('explanation')}")
        print(f"[Aegis - Blue Team Agent] 📈 Confidence Score: {data.get('confidence_score')}/100")
        safe_code = data.get('secure_code', '').strip()
        with open(output_fixed_path, 'w') as f:
            f.write(safe_code)
        print(f"[Aegis - Blue Team Agent] 🛡️ Secure refactoring complete!")
        return True
    except Exception as e:
        print(f"[Aegis - Blue Team Agent] Error: {e}")
        return False
