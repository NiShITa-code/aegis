import pytest
import os
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import app_config
from app_config import TenantConfig
from pydantic import SecretStr
from server import app
from reporter import AegisReporter, OrchestratorArtifact, ScanReport

client = TestClient(app)

# Helper: patch tenant config so dashboard tests can authenticate
def _test_tenant_config():
    return {
        "test_tenant": TenantConfig(api_key=SecretStr("test-api-key"), repos=["*"])
    }

TEST_AUTH_HEADER = {"Authorization": "Bearer test-api-key"}

def test_scan_report_is_created_for_secured_result(tmp_path):
    reporter = AegisReporter("scan_123")
    reporter.reports_dir = str(tmp_path)
    reporter.scan_targets = ["file.py"]
    
    art = OrchestratorArtifact(
        target_file="file.py",
        status="SECURED",
        sandbox_output="Blocked!",
        original_code="bad",
        exploit_code="attack",
        patched_code="good"
    )
    reporter.add_orchestrator_artifact(art)
    reporter.save()
    
    report_path = tmp_path / "scan_123.json"
    assert report_path.exists()
    
    with open(report_path) as f:
        data = json.load(f)
        assert data["final_status"] == "SECURED"
        assert len(data["orchestrator_results"]) == 1

def test_scan_report_is_created_for_failed_result(tmp_path):
    reporter = AegisReporter("scan_fail")
    reporter.reports_dir = str(tmp_path)
    reporter.scan_targets = ["file.py"]
    
    art = OrchestratorArtifact(
        target_file="file.py",
        status="LLM_FAILURE",
        sandbox_output="",
        original_code="",
        exploit_code="",
        patched_code=""
    )
    reporter.add_orchestrator_artifact(art)
    reporter.save()
    
    report_path = tmp_path / "scan_fail.json"
    with open(report_path) as f:
        data = json.load(f)
        assert data["final_status"] == "LLM_FAILURE"

def test_report_contains_skipped_file_reasons(tmp_path):
    reporter = AegisReporter("scan_skip")
    reporter.reports_dir = str(tmp_path)
    reporter.skipped_files = {"secret.py": "LIKELY_SECRET"}
    reporter.save()
    
    with open(tmp_path / "scan_skip.json") as f:
        data = json.load(f)
        assert data["skipped_files"]["secret.py"] == "LIKELY_SECRET"

def test_report_contains_budget_usage(tmp_path):
    reporter = AegisReporter("scan_budget")
    reporter.reports_dir = str(tmp_path)
    
    art = OrchestratorArtifact(
        target_file="file.py",
        status="SECURED",
        sandbox_output="", original_code="", exploit_code="", patched_code="",
        llm_calls=5,
        token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    )
    reporter.add_orchestrator_artifact(art)
    reporter.save()
    
    with open(tmp_path / "scan_budget.json") as f:
        data = json.load(f)
        assert data["budget_usage"]["total_llm_calls"] == 5
        assert data["budget_usage"]["total_tokens"] == 150

def test_report_redacts_secrets(tmp_path):
    reporter = AegisReporter("scan_redact")
    reporter.reports_dir = str(tmp_path)
    
    art = OrchestratorArtifact(
        target_file="file.py",
        status="SECURED",
        sandbox_output="Error with API_KEY: 12345", 
        original_code="password=secret123", 
        exploit_code="ghp_123456789012345678901234567890123456", 
        patched_code="sk-123456789012345678901234567890123456"
    )
    reporter.add_orchestrator_artifact(art)
    reporter.save()
    
    with open(tmp_path / "scan_redact.json") as f:
        data = json.load(f)
        res = data["orchestrator_results"][0]
        assert "12345" not in res["sandbox_output"]
        assert "secret123" not in res["original_code"]
        assert "ghp_" not in res["exploit_code"]
        assert "sk-" not in res["patched_code"]

def test_report_excludes_raw_prompts_by_default(tmp_path):
    # We do not store raw prompts in the OrchestratorArtifact
    # This test verifies prompts aren't leaking
    reporter = AegisReporter("scan_no_prompts")
    reporter.reports_dir = str(tmp_path)
    reporter.add_orchestrator_artifact(OrchestratorArtifact(
        target_file="f.py", status="SECURED", sandbox_output="", original_code="", exploit_code="", patched_code=""
    ))
    reporter.save()
    
    with open(tmp_path / "scan_no_prompts.json") as f:
        content = f.read()
        assert "system prompt" not in content.lower()

def test_dashboard_api_returns_scan_history(tmp_path):
    with patch.object(app_config.settings, 'tenant_config', _test_tenant_config()), \
         patch('server.os.path.exists', return_value=True), \
         patch('server.glob.glob', return_value=["1.json", "2.json"]), \
         patch('builtins.open', mock_open_reports):
         
        response = client.get("/api/reports", headers=TEST_AUTH_HEADER)
        assert response.status_code == 200
        assert "reports" in response.json()

def mock_open_reports(file, *args, **kwargs):
    if "1.json" in file:
        return MagicMock(__enter__=lambda x: MagicMock(read=lambda: '{"id": "1", "timestamp": "2023-01-01"}'))
    return MagicMock(__enter__=lambda x: MagicMock(read=lambda: '{"id": "2", "timestamp": "2023-01-02"}'))

def test_dashboard_api_returns_single_scan_detail():
    with patch.object(app_config.settings, 'tenant_config', _test_tenant_config()), \
         patch('server.os.path.exists', return_value=True), \
         patch('builtins.open', mock_open_reports):
        response = client.get("/api/reports/1", headers=TEST_AUTH_HEADER)
        assert response.status_code == 200

def test_markdown_summary_matches_json_status(tmp_path):
    reporter = AegisReporter("scan_md")
    reporter.reports_dir = str(tmp_path)
    reporter.scan_targets = ["file.py"]
    reporter.add_orchestrator_artifact(OrchestratorArtifact(
        target_file="file.py", status="SECURED", sandbox_output="", original_code="", exploit_code="", patched_code=""
    ))
    reporter.save()
    
    md_path = tmp_path / "scan_md.md"
    assert md_path.exists()
    assert "`SECURED`" in md_path.read_text()

def test_atomic_report_writes_prevent_corruption(tmp_path):
    import orchestrator
    
    # Create a dummy file
    dummy_file = tmp_path / "dummy.py"
    dummy_file.write_text("print('test')")
    
    with patch('orchestrator.os.environ', {"AEGIS_ORCHESTRATOR_OUTPUT_JSON": str(tmp_path / "out.json")}), \
         patch('orchestrator.os.replace') as mock_replace, \
         patch('orchestrator.generate_exploit') as mock_exploit, \
         patch('orchestrator.run_exploit_against_target') as mock_run_exp, \
         patch('orchestrator.generate_fix') as mock_fix, \
         patch('orchestrator.validate_safe_path'):
         
        # Make red team succeed
        mock_exploit.return_value = (True, {"cwe_id": "CWE-79"})
        mock_run_exp.side_effect = [(True, "Vulnerable!"), (True, "Still vulnerable!"), (True, "Still vulnerable!"), (True, "Still vulnerable!")]
        
        # Make blue team succeed in generating, but sandbox says it's STILL vulnerable
        mock_fix.return_value = (True, {})
        
        with patch('llm_utils.LLM_TELEMETRY', {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_calls": 0}):
            try:
                orchestrator.run_aegis_pipeline(str(dummy_file))
            except SystemExit:
                pass
            
        assert mock_replace.called
        args = mock_replace.call_args[0]
        assert str(args[0]).endswith(".tmp")

def test_corrupted_intermediate_artifacts_are_handled(tmp_path):
    from server import process_pr_sync
    from unittest.mock import mock_open
    
    # We mock out clone_pr_branch and everything to just simulate parsing an invalid JSON
    with patch('server.clone_pr_branch', return_value=True), \
         patch('server.get_pr_changed_files', return_value=["f.py"]), \
         patch('server.RepositoryScanner') as mock_scan, \
         patch('server.run_semgrep', return_value=["f.py"]), \
         patch('server.subprocess.run'), \
         patch('server.os.makedirs'), \
         patch('server.shutil'), \
         patch('server.os.path.exists', side_effect=lambda path: True if path.endswith('.json') else os.path.exists(path)), \
         patch('builtins.open', mock_open(read_data='{bad json')), \
         patch('server.AegisReporter') as mock_rep:
         
        mock_scan.return_value.get_scan_targets.return_value = ["f.py"]
        mock_scan.return_value.skipped_files = {}
        mock_scan.return_value.budgets = {"max_vulnerabilities": 5}
        
        process_pr_sync("repo", 1)
        # It shouldn't crash, it should handle the corrupted artifact
        assert mock_rep.return_value.add_orchestrator_artifact.called

def test_report_pagination_limits_enforced():
    # glob returns 100 items, default limit is 50
    with patch.object(app_config.settings, 'tenant_config', _test_tenant_config()), \
         patch('server.os.path.exists', return_value=True), \
         patch('server.glob.glob', return_value=[f"{i}.json" for i in range(100)]), \
         patch('builtins.open', mock_open_reports):
         
        response = client.get("/api/reports", headers=TEST_AUTH_HEADER)
        assert len(response.json()["reports"]) == 50

def test_final_status_derived_from_validated_artifacts(tmp_path):
    reporter = AegisReporter("scan_derive")
    reporter.reports_dir = str(tmp_path)
    reporter.scan_targets = ["a.py", "b.py"]
    
    # 1 secured, 1 failed
    reporter.add_orchestrator_artifact(OrchestratorArtifact(
        target_file="a.py", status="SECURED", sandbox_output="", original_code="", exploit_code="", patched_code=""
    ))
    reporter.add_orchestrator_artifact(OrchestratorArtifact(
        target_file="b.py", status="TIMEOUT", sandbox_output="", original_code="", exploit_code="", patched_code=""
    ))
    
    rep = reporter.build_report()
    # Final status should be TIMEOUT because not all were secured
    assert rep.final_status == "TIMEOUT"
