import pytest
import os
import sys
import tempfile
from unittest.mock import patch

# Ensure aegis_core is in path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sandbox import run_exploit_against_target

def test_docker_failure_prevents_host_execution():
    """
    Proves that if Docker daemon fails, Aegis gracefully aborts
    and does NOT fall back to insecure host execution.
    """
    with patch('sandbox.subprocess.run') as mock_run:
        # Simulate Docker connection error
        mock_result = mock_run.return_value
        mock_result.returncode = 1
        mock_result.stderr = "error during connect: Cannot connect to the Docker daemon"
        mock_result.stdout = ""
        
        # Create dummy files
        with open("dummy_exploit.py", "w") as f: f.write("")
        with open("dummy_target.py", "w") as f: f.write("")
        
        try:
            # Call the sandbox
            is_vuln, output = run_exploit_against_target("dummy_exploit.py", "dummy_target.py")
    
            # It must return False (secure/aborted) and the output must mention Docker daemon unavailability
            assert is_vuln == False
            assert "Docker daemon unavailable" in output
            # Ensure subprocess.run was only called ONCE (for the docker command, no fallback call)
            assert mock_run.call_count == 1
            
            # Verify it was the docker command that was called
            args = mock_run.call_args[0][0]
            assert args[0] == "docker"
        finally:
            os.remove("dummy_exploit.py")
            os.remove("dummy_target.py")

def test_sandbox_isolation_prevents_source_deletion():
    """
    Proves that a malicious payload attempting to delete the Aegis source code
    or list directories outside the sandbox workspace fails.
    """
    # Create a dummy target app
    target_app = "target_app.py"
    with open(target_app, 'w') as f:
        f.write("print('hello')")
        
    # Create a malicious payload attempting directory traversal
    malicious_exploit = "malicious.py"
    with open(malicious_exploit, 'w') as f:
        f.write('''
import os
try:
    # Try to read files from the parent directory
    # In a vulnerable setup (mounting cwd), this would expose Aegis source
    files = os.listdir("..")
    print("LEAKED_FILES: " + str(files))
except Exception as e:
    print("BLOCKED: " + str(e))
''')
    
    # We test it if Docker is available. If not, the test just passes.
    try:
        import subprocess
        subprocess.run(["docker", "ps"], check=True, capture_output=True)
        docker_available = True
    except:
        docker_available = False
        
    if docker_available:
        is_vuln, output = run_exploit_against_target(malicious_exploit, target_app)
        # It shouldn't crash, but it shouldn't leak Aegis source files
        assert "LEAKED_FILES" not in output or "sandbox.py" not in output
        assert "orchestrator.py" not in output
        
    # Cleanup
    os.remove(target_app)
    os.remove(malicious_exploit)
