import pytest
import os
import sys
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from orchestrator import run_aegis_pipeline

def test_destructive_patch_is_rejected(tmp_path):
    """
    Proves that if a patch blocks the exploit but breaks functional tests (e.g. sys.exit()),
    it is rejected by the orchestrator and triggers self-healing retry.
    """
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    target_file = "dummy_target.py"
    with open(target_file, "w") as f:
        f.write("def my_func(): return True")
        
    # Setup a functional test command that FAILS
    # We create a dummy aegis.yml
    with open("aegis.yml", "w") as f:
        # A test command that always fails
        f.write("test_command: 'python -c \"import sys; sys.exit(1)\"'")
        
    with patch('orchestrator.generate_exploit') as mock_gen_exp, \
         patch('orchestrator.run_exploit_against_target') as mock_run_exp, \
         patch('orchestrator.generate_fix') as mock_gen_fix:
         
        # Red Team successfully generates exploit
        mock_gen_exp.return_value = True
        with open("generated_exploit.py", "w") as f: f.write("")
        
        # Phase 2: Sandbox says YES it's vulnerable on first try
        # Phase 4: Sandbox says NO it's not vulnerable anymore on subsequent tries
        # So we return (True, "Vuln") for Phase 2, then (False, "Safe") for Phase 4
        mock_run_exp.side_effect = [(True, "Vulnerable!"), (False, "Secured!"), (False, "Secured!"), (False, "Secured!")]
        
        # Blue Team successfully generates a fix
        mock_gen_fix.return_value = True
        with open("dummy_target_secure.py", "w") as f: f.write("import sys; sys.exit(0)")

        # It should try 3 times and then sys.exit(1) because tests always fail
        with pytest.raises(SystemExit) as e:
            run_aegis_pipeline(target_file)
            
        assert e.value.code == 1
        
        # Ensure it retried 3 times (Max retries)
        assert mock_gen_fix.call_count == 3
        
        # Make sure the previous_error passed back contains the test failure string
        last_call_args = mock_gen_fix.call_args[0]
        assert "BROKE the functional tests" in last_call_args[3]
        
    os.chdir(original_cwd)
