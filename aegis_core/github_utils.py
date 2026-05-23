import os
import subprocess
from github import Github
from github.PullRequest import PullRequest

def get_github_client():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("[Aegis - GitHub] Warning: GITHUB_TOKEN not set. API calls will fail.")
        return Github()
    return Github(token)

def clone_pr_branch(repo_full_name: str, pr_number: int, target_dir: str) -> bool:
    """
    Clones the repository and checks out the specific PR branch into target_dir.
    """
    try:
        # Example URL: https://github.com/NiShITa-code/aegis.git
        # If GITHUB_TOKEN is present, we inject it for private repo access
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            repo_url = f"https://{token}@github.com/{repo_full_name}.git"
        else:
            repo_url = f"https://github.com/{repo_full_name}.git"
            
        print(f"[Aegis - GitHub] Cloning PR #{pr_number} from {repo_full_name}...")
        
        # Clone the repo
        subprocess.run(["git", "clone", repo_url, target_dir], check=True, capture_output=True)
        
        # Fetch the PR branch
        subprocess.run(
            ["git", "fetch", "origin", f"pull/{pr_number}/head:pr-{pr_number}"],
            cwd=target_dir, check=True, capture_output=True
        )
        
        # Checkout the PR branch
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
        g = get_github_client()
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(body)
        print(f"[Aegis - GitHub] Successfully posted comment to PR #{pr_number}")
    except Exception as e:
        print(f"[Aegis - GitHub] Failed to post PR comment: {e}")

def create_commit_on_pr(target_dir: str, file_path: str, commit_message: str):
    """
    Commits a generated secure patch back to the PR branch.
    Note: file_path should be relative to target_dir.
    """
    try:
        subprocess.run(["git", "add", file_path], cwd=target_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", commit_message], cwd=target_dir, check=True, capture_output=True)
        # Push back (requires write permissions on the branch)
        # subprocess.run(["git", "push"], cwd=target_dir, check=True, capture_output=True)
        print(f"[Aegis - GitHub] Created commit for {file_path}")
        return True
    except Exception as e:
        print(f"[Aegis - GitHub] Error committing patch: {e}")
        return False
