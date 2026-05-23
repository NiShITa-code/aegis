import subprocess
import json
import os
from typing import List

class SASTFailedError(Exception):
    pass

def run_semgrep(targets: List[str]) -> List[str]:
    """
    Runs Semgrep SAST on the provided targets list to identify potentially vulnerable files.
    Fails closed if Semgrep crashes or is unavailable.
    """
    if not targets:
        return []
        
    print(f"[Aegis - Discovery] Running Semgrep SAST on {len(targets)} files...")
    
    # Verify semgrep is installed
    try:
        subprocess.run(["semgrep", "--version"], capture_output=True, check=True)
    except Exception as e:
        raise SASTFailedError(f"Semgrep is not installed, not found, or crashed: {e}")

    # Run semgrep with auto config on specific files
    try:
        cmd = ["semgrep", "scan", "--config", "auto", "--json"] + targets
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False # Semgrep returns non-zero if it finds issues
        )
        
        output = result.stdout
        if not output:
            if result.stderr:
                raise SASTFailedError(f"Semgrep returned no output. Error: {result.stderr}")
            raise SASTFailedError("Semgrep returned no output and no error.")
            
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            raise SASTFailedError(f"Failed to parse Semgrep JSON output: {e}. Output was: {output[:200]}")
            
        results = data.get("results", [])
        vulnerable_files = set()
        
        for r in results:
            path = r.get("path")
            if path:
                abs_path = os.path.abspath(path)
                # Only include files that were in our explicit targets list (or their absolute equivalents)
                abs_targets = [os.path.abspath(t) for t in targets]
                if abs_path in abs_targets:
                    vulnerable_files.add(abs_path)
                
        print(f"[Aegis - Discovery] Semgrep found potential issues in {len(vulnerable_files)} files.")
        return list(vulnerable_files)

    except Exception as e:
        if isinstance(e, SASTFailedError):
            raise
        raise SASTFailedError(f"Exception running Semgrep: {e}")
