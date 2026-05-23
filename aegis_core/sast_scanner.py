import subprocess
import json
import os
from typing import List

def run_semgrep(directory_path: str) -> List[str]:
    """
    Runs Semgrep SAST on a given directory to quickly identify potentially vulnerable files.
    This acts as a fast pre-filter so the heavy LLM Red Team Agent only focuses on files
    that are highly likely to contain vulnerabilities.
    """
    print(f"[Aegis - Discovery] Running Semgrep SAST on {directory_path}...")
    
    # Verify semgrep is installed
    try:
        subprocess.run(["semgrep", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[Aegis - Discovery] Warning: semgrep not found. Skipping pre-filter.")
        # Fallback to returning all python files if semgrep is missing
        return _fallback_scan(directory_path)

    # Run semgrep with auto config
    try:
        result = subprocess.run(
            ["semgrep", "scan", "--config", "auto", "--json", directory_path],
            capture_output=True,
            text=True,
            check=False # Semgrep returns non-zero if it finds issues
        )
        
        output = result.stdout
        if not output:
            print("[Aegis - Discovery] Error: Semgrep returned no output.")
            return []
            
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            # If semgrep prints some other info before the JSON, try to extract JSON
            print(f"[Aegis - Discovery] Failed to parse Semgrep JSON output: {e}")
            return _fallback_scan(directory_path)
            
        results = data.get("results", [])
        vulnerable_files = set()
        
        for r in results:
            path = r.get("path")
            if path:
                # Ensure we return absolute paths for the rest of the pipeline
                abs_path = os.path.abspath(os.path.join(directory_path, path))
                vulnerable_files.add(abs_path)
                
        print(f"[Aegis - Discovery] Semgrep found potential issues in {len(vulnerable_files)} files.")
        return list(vulnerable_files)

    except Exception as e:
        print(f"[Aegis - Discovery] Exception running Semgrep: {e}")
        return _fallback_scan(directory_path)

def _fallback_scan(directory_path: str) -> List[str]:
    """Fallback if semgrep fails: just return all .py files."""
    files = []
    for root, _, filenames in os.walk(directory_path):
        for f in filenames:
            if f.endswith(".py"):
                files.append(os.path.abspath(os.path.join(root, f)))
    return files

if __name__ == "__main__":
    # Test it on the current directory
    res = run_semgrep(".")
    print("Vulnerable files:", res)
