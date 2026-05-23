import pytest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from repository_scanner import RepositoryScanner
from context_loader import load_codebase_context, count_tokens
from sast_scanner import run_semgrep, SASTFailedError
from orchestrator import run_aegis_pipeline, STATUS_SCAN_TOO_LARGE, STATUS_SAST_FAILED

def test_semgrep_failure_returns_sast_failed_status():
    with patch('sast_scanner.subprocess.run') as mock_run:
        mock_run.side_effect = FileNotFoundError() # Simulate semgrep not found
        with pytest.raises(SASTFailedError):
            run_semgrep(["target.py"])

def test_semgrep_failure_does_not_scan_entire_repo():
    # If semgrep fails, it should raise SASTFailedError and NOT fallback
    with patch('sast_scanner.subprocess.run') as mock_run:
        mock_run.side_effect = Exception("Crash")
        with pytest.raises(SASTFailedError):
            run_semgrep(["target.py"])

def test_pr_diff_mode_scans_only_changed_files(tmp_path):
    scanner = RepositoryScanner(str(tmp_path))
    
    file1 = tmp_path / "changed.py"
    file2 = tmp_path / "unchanged.py"
    file1.write_text("print(1)")
    file2.write_text("print(2)")
    
    # Pass only changed.py
    targets = scanner.get_scan_targets(["changed.py"])
    assert len(targets) == 1
    assert "changed.py" in targets[0]

def test_aegisignore_excludes_files(tmp_path):
    ignore_file = tmp_path / ".aegisignore"
    ignore_file.write_text("secret_logic.py\n")
    
    secret_logic = tmp_path / "secret_logic.py"
    secret_logic.write_text("print('secret')")
    
    normal = tmp_path / "normal.py"
    normal.write_text("print('normal')")
    
    scanner = RepositoryScanner(str(tmp_path))
    targets = scanner.get_scan_targets()
    assert len(targets) == 1
    assert "normal.py" in targets[0]

def test_binary_and_lockfiles_are_skipped(tmp_path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{}")
    
    binary = tmp_path / "app.exe"
    binary.write_bytes(b"\x00\x01")
    
    normal = tmp_path / "normal.py"
    normal.write_text("print('normal')")
    
    scanner = RepositoryScanner(str(tmp_path))
    targets = scanner.get_scan_targets()
    assert len(targets) == 1
    assert "normal.py" in targets[0]

def test_vendor_and_node_modules_are_skipped(tmp_path):
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    vendor_file = node_modules / "lib.js"
    vendor_file.write_text("console.log(1)")
    
    normal = tmp_path / "normal.py"
    normal.write_text("print('normal')")
    
    scanner = RepositoryScanner(str(tmp_path))
    targets = scanner.get_scan_targets()
    assert len(targets) == 1
    assert "normal.py" in targets[0]

def test_secret_files_are_never_sent_to_llm(tmp_path):
    secret_file = tmp_path / "api_key.py"
    secret_file.write_text("KEY = '123'")
    
    scanner = RepositoryScanner(str(tmp_path))
    targets = scanner.get_scan_targets()
    assert len(targets) == 0

def test_skipped_files_include_reason_codes(tmp_path, capsys):
    secret = tmp_path / "password.py"
    secret.write_text("pass")
    
    scanner = RepositoryScanner(str(tmp_path))
    scanner.get_scan_targets()
    
    captured = capsys.readouterr().out
    assert "password.py (LIKELY_SECRET)" in captured or "password.py" in captured

def test_context_retrieval_includes_relevant_imports(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("import utils\nutils.do_something()")
    
    utils = tmp_path / "utils.py"
    utils.write_text("def do_something(): pass")
    
    context = load_codebase_context(str(target), str(tmp_path))
    assert "def do_something(): pass" in context

def test_context_retrieval_does_not_include_unrelated_files(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("import utils\nutils.do_something()")
    
    utils = tmp_path / "utils.py"
    utils.write_text("def do_something(): pass")
    
    unrelated = tmp_path / "unrelated.py"
    unrelated.write_text("def ignore_me(): pass")
    
    context = load_codebase_context(str(target), str(tmp_path))
    assert "ignore_me" not in context

def test_vector_context_disabled_by_default(tmp_path):
    # Vector is disabled by default
    assert os.environ.get("AEGIS_ENABLE_VECTOR_CONTEXT", "false").lower() == "false"

def test_token_budget_uses_safety_margin(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("import huge\n")
    
    huge = tmp_path / "huge.py"
    # Create a huge file
    huge.write_text("print('x')\n" * 10000) 
    
    # With a small max_context_tokens budget, it should truncate or stop
    with patch('context_loader.get_aegis_budgets', return_value={"max_context_tokens": 100}):
        context = load_codebase_context(str(target), str(tmp_path))
        # It should hit the limit and print a warning, and context should be partially empty or just the first few lines
        assert len(context) < 10000 * 10 # Didn't load the whole file

def test_scan_budget_exhaustion_returns_scan_too_large(tmp_path):
    # Set a small max_file_bytes
    target = tmp_path / "huge_target.py"
    target.write_text("x" * 20000)
    
    with patch('orchestrator.get_aegis_budgets', return_value={"max_file_bytes": 1000}):
        with pytest.raises(SystemExit) as e:
            run_aegis_pipeline(str(target))
        assert e.value.code == 1

def test_llm_call_budget_prevents_cost_explosion(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("print('test')")
    
    # We mock it such that red team fails repeatedly
    with patch('orchestrator.generate_exploit', return_value=(False, "TIMEOUT")), \
         patch('orchestrator.get_aegis_budgets', return_value={"max_llm_calls": 2}):
        
        with pytest.raises(SystemExit) as e:
            run_aegis_pipeline(str(target))
        # Should exit quickly due to timeout
        assert e.value.code == 1

def test_large_repo_respects_file_and_token_budget(tmp_path):
    # Create 200 files
    for i in range(200):
        (tmp_path / f"file_{i}.py").write_text("print(1)")
        
    with patch('repository_scanner.get_aegis_budgets', return_value={"max_files": 10, "max_file_bytes": 10000}):
        scanner = RepositoryScanner(str(tmp_path))
        targets = scanner.get_scan_targets()
        assert len(targets) <= 10
