import os
import subprocess
import time
from github import Github, Auth

def get_github_token(repo_full_name=None) -> str:
    app_id = os.environ.get("GITHUB_APP_ID")
    private_key = os.environ.get("GITHUB_APP_PRIVATE_KEY")
    
    if app_id and private_key and repo_full_name:
        try:
            from github import GithubIntegration
            auth = Auth.AppAuth(app_id, private_key)
            gi = GithubIntegration(auth=auth)
            owner, repo_name = repo_full_name.split("/")
            installation = gi.get_installation(owner, repo_name)
            token_obj = gi.get_access_token(installation.id)
            return token_obj.token
        except Exception as e:
            print(f"[Aegis - GitHub] Failed to get App installation token: {e}")

    env = os.environ.get("AEGIS_ENV", "production")
    allow_pat = os.environ.get("AEGIS_ALLOW_PAT_FALLBACK", "false").lower() == "true"
    
    if env == "development" or allow_pat:
        return os.environ.get("GITHUB_TOKEN", "")
        
    print("[Aegis - GitHub] Error: No valid authentication available. (App Auth missing and PAT fallback not allowed in production).")
    return ""

def get_github_client(repo_full_name=None):
    token = get_github_token(repo_full_name)
    if not token:
        return Github()
    return Github(token)

def clone_pr_branch(repo_full_name: str, pr_number: int, target_dir: str) -> bool:
    """
    Clones the repository and checks out the specific PR branch into target_dir.
    """
    try:
        token = get_github_token(repo_full_name)
        if token:
            # Use x-access-token for App tokens, it works for PATs too usually
            repo_url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
        else:
            repo_url = f"https://github.com/{repo_full_name}.git"
            
        print(f"[Aegis - GitHub] Cloning PR #{pr_number} from {repo_full_name}...")
        
        subprocess.run(["git", "clone", repo_url, target_dir], check=True, capture_output=True)
        
        subprocess.run(
            ["git", "fetch", "origin", f"pull/{pr_number}/head:pr-{pr_number}"],
            cwd=target_dir, check=True, capture_output=True
        )
        
        subprocess.run(
            ["git", "checkout", f"pr-{pr_number}"],
            cwd=target_dir, check=True, capture_output=True
        )
        
        return True
    except Exception as e:
        print(f"[Aegis - GitHub] Error cloning PR: {e}")
        return False

def post_pr_comment(repo_full_name: str, pr_number: int, body: str):
    """
    Posts a review comment on the PR.
    """
    try:
        g = get_github_client(repo_full_name)
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(body)
        print(f"[Aegis - GitHub] Successfully posted comment to PR #{pr_number}")
    except Exception as e:
        print(f"[Aegis - GitHub] Failed to post PR comment: {e}")

def apply_patch(target_dir: str, file_paths: list, commit_message: str, repo_full_name: str, pr_number: int):
    """
    Commits a generated secure patch back to the PR branch or creates a new patch PR if unsafe.
    """
    try:
        for f in file_paths:
            subprocess.run(["git", "add", f], cwd=target_dir, check=True, capture_output=True)
            
        # Check if diff is empty
        status = subprocess.run(["git", "status", "--porcelain"], cwd=target_dir, capture_output=True, text=True)
        if not status.stdout.strip():
            print("[Aegis - GitHub] Empty diff. Patch aborted.")
            return False
            
        subprocess.run(["git", "commit", "-m", commit_message], cwd=target_dir, check=True, capture_output=True)
        
        g = get_github_client(repo_full_name)
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        
        safe = False
        if pr.state == "open" and not pr.merged and pr.head.repo.full_name == pr.base.repo.full_name:
            try:
                branch = repo.get_branch(pr.head.ref)
                if not branch.protected:
                    safe = True
            except Exception as e:
                print(f"[Aegis - GitHub] Error checking branch protection: {e}")

        token = get_github_token(repo_full_name)
        if not token:
            print("[Aegis - GitHub] Missing write token.")
            return False
            
        repo_url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
        
        if safe:
            subprocess.run(["git", "push", repo_url, f"HEAD:{pr.head.ref}"], cwd=target_dir, check=True, capture_output=True)
            print(f"[Aegis - GitHub] Directly pushed patch to PR #{pr_number}")
            return True
        else:
            branch_name = f"aegis-patch-PR{pr_number}-{int(time.time())}"
            # Push to base repo
            subprocess.run(["git", "push", repo_url, f"HEAD:refs/heads/{branch_name}"], cwd=target_dir, check=True, capture_output=True)
            
            # Create new PR
            new_pr = repo.create_pull(
                title=f"Aegis Security Patch for PR #{pr_number}",
                body=f"This PR contains a generated security patch for #{pr_number}.",
                base=pr.base.ref,
                head=branch_name
            )
            
            # Comment on original PR
            pr.create_issue_comment(f"Aegis generated a validated security patch, but could not push directly to this PR because the source branch is forked or protected. A separate patch PR has been opened here: #{new_pr.number}.")
            print(f"[Aegis - GitHub] Created fallback PR #{new_pr.number}")
            return True
            
    except Exception as e:
        print(f"[Aegis - GitHub] Error applying patch: {e}")
        return False
