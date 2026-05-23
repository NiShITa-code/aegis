import os
from pydantic import BaseModel, Field
from llm_utils import safe_call_llm

class RemediationPayload(BaseModel):
    # Confidence is provided but determinism/proof depends strictly on orchestrator
    confidence_score: int = Field(description="Confidence from 1-100 that this code mathematically patches the vulnerability.")
    explanation: str = Field(description="A 1-sentence explanation of what was changed.")
    secure_code: str = Field(description="The raw, entirely refactored application code.")

def generate_fix(target_code_path: str, exploit_path: str, output_fixed_path: str, previous_error: str = None):
    """
    Reads vulnerable code and exploit, uses an LLM to generate secure code via Structured JSON.
    Returns (success_bool, status_code).
    """
    print("[Aegis - Blue Team Agent] Formulating a secure patch with strict schema adherence...")
    
    try:
        with open(target_code_path, 'r') as f:
            target_code = f.read()
            
        with open(exploit_path, 'r') as f:
            exploit_code = f.read()
    except Exception as e:
        print(f"[Aegis - Blue Team Agent] Could not read files: {e}")
        return False, "READ_ERROR"

    prompt = f"""You are an elite defensive security engineer (Blue Team).
    A Red Team agent has exploited the application using the provided exploit script.
    Your task is to refactor the application to mitigate this vulnerability.
    
    --- ORIGINAL VULNERABLE CODE ---
    {target_code}
    
    --- RED TEAM EXPLOIT SCRIPT USED ---
    {exploit_code}
    """
    
    if previous_error:
        prompt += f"\n    --- FEEDBACK ON PREVIOUS PATCH ---\n    Your previous patch FAILED. The sandbox was still exploited, or functional tests broke. Docker/Test Output:\n    {previous_error}\n    Fix the flaws in your logic and try completely replacing it.\n"

    messages = [
        {"role": "system", "content": "You are a cybersecurity tool that outputs ONLY valid JSON matching the schema."},
        {"role": "user", "content": prompt}
    ]

    data, status_code = safe_call_llm(messages, RemediationPayload)
    
    if status_code != "SUCCESS" or not data:
        print(f"[Aegis - Blue Team Agent] Failed to generate fix. Status: {status_code}")
        return False, status_code
        
    print(f"[Aegis - Blue Team Agent] 🛠️ Fix Plan: {data.explanation}")
    print(f"[Aegis - Blue Team Agent] 📈 Confidence Score: {data.confidence_score}/100 (Note: Aegis does not trust confidence as proof. Verifying...)")
    
    safe_code = data.secure_code.strip()
    
    if not safe_code:
        print("[Aegis - Blue Team Agent] Error: Generated secure code is empty.")
        return False, "EMPTY_PATCH"
        
    try:
        with open(output_fixed_path, 'w') as f:
            f.write(safe_code)
    except Exception as e:
        print(f"[Aegis - Blue Team Agent] Could not write secure code: {e}")
        return False, "WRITE_ERROR"
        
    print(f"[Aegis - Blue Team Agent] 🛡️ Secure refactoring complete! Saved to {output_fixed_path}.")
    return True, "SUCCESS"

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        print("Usage: python agent_blue.py <vulnerable_app.py> <exploit.py> <output_fixed_app.py>")
    else:
        generate_fix(sys.argv[1], sys.argv[2], sys.argv[3])
