import pytest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from github_utils import get_github_token, apply_patch
from idempotency import SQLiteIdempotencyStore

def test_github_token_fallback_blocked_in_production(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_pat")
    monkeypatch.setenv("AEGIS_ENV", "production")
    monkeypatch.delenv("AEGIS_ALLOW_PAT_FALLBACK", raising=False)
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    
    token = get_github_token("owner/repo")
    assert token == "" # Fallback is blocked

def test_github_token_fallback_allowed_in_dev(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_pat")
    monkeypatch.setenv("AEGIS_ENV", "development")
    
    token = get_github_token("owner/repo")
    assert token == "fake_pat"

def test_idempotency_store(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = SQLiteIdempotencyStore(db_path=db_path)
    
    assert not store.is_processed("delivery-123")
    store.mark_processed("delivery-123")
    assert store.is_processed("delivery-123")
    
    # Should not crash on duplicate insertion
    store.mark_processed("delivery-123")

@patch('github_utils.get_github_client')
@patch('github_utils.get_github_token')
@patch('subprocess.run')
def test_apply_patch_direct_push_safe(mock_subproc, mock_token, mock_client, tmp_path):
    mock_token.return_value = "token"
    
    mock_g = MagicMock()
    mock_client.return_value = mock_g
    mock_repo = MagicMock()
    mock_g.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    
    mock_pr.state = "open"
    mock_pr.merged = False
    mock_pr.head.repo.full_name = "owner/repo"
    mock_pr.base.repo.full_name = "owner/repo"
    
    mock_branch = MagicMock()
    mock_branch.protected = False
    mock_repo.get_branch.return_value = mock_branch
    
    # Mock subprocess for git status to show diff
    mock_subproc.return_value.stdout = "M  file.py"
    
    result = apply_patch(str(tmp_path), ["file.py"], "msg", "owner/repo", 1)
    
    assert result == True
    # Verify git push was called with direct HEAD mapping
    push_call = [call for call in mock_subproc.call_args_list if "push" in call[0][0]]
    assert len(push_call) == 1
    assert f"HEAD:{mock_pr.head.ref}" in push_call[0][0][0]

@patch('github_utils.get_github_client')
@patch('github_utils.get_github_token')
@patch('subprocess.run')
def test_apply_patch_fork_creates_pr(mock_subproc, mock_token, mock_client, tmp_path):
    mock_token.return_value = "token"
    
    mock_g = MagicMock()
    mock_client.return_value = mock_g
    mock_repo = MagicMock()
    mock_g.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    
    mock_pr.state = "open"
    mock_pr.merged = False
    mock_pr.head.repo.full_name = "fork/repo"
    mock_pr.base.repo.full_name = "owner/repo"
    
    mock_subproc.return_value.stdout = "M  file.py"
    
    result = apply_patch(str(tmp_path), ["file.py"], "msg", "owner/repo", 1)
    
    assert result == True
    
    # Ensure it created a patch PR
    mock_repo.create_pull.assert_called_once()
    mock_pr.create_issue_comment.assert_called_once()

@patch('subprocess.run')
def test_apply_patch_aborts_on_empty_diff(mock_subproc, tmp_path):
    # Mock subprocess for git status to show NO diff
    mock_subproc.return_value.stdout = ""
    
    result = apply_patch(str(tmp_path), ["file.py"], "msg", "owner/repo", 1)
    
    assert result == False
