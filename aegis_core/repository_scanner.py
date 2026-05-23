import os
import subprocess
from config import get_aegis_budgets

class RepositoryScanner:
    """
    Intelligently scans the repository, enforcing ignore lists, budgets, and PR context.
    """
    def __init__(self, repo_dir: str):
        self.repo_dir = os.path.abspath(repo_dir)
        self.budgets = get_aegis_budgets(self.repo_dir)
        
        self.ignored_dirs = {'venv', '__pycache__', '.git', 'node_modules', 'vendor', 'dist', 'build', 'out', 'bin', 'obj'}
        self.ignored_extensions = {'.pyc', '.exe', '.dll', '.so', '.dylib', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.tar', '.gz'}
        self.ignored_files = {'package-lock.json', 'yarn.lock', 'Gemfile.lock', 'poetry.lock'}
        self.secret_keywords = ['secret', 'key', 'token', 'password', 'credential', 'cert', 'pem']
        
        self.aegis_ignore = self._load_ignore_file('.aegisignore')
        self.git_ignore = self._load_ignore_file('.gitignore')
        
    def _load_ignore_file(self, filename: str) -> list:
        filepath = os.path.join(self.repo_dir, filename)
        ignores = []
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        ignores.append(line)
        return ignores
        
    def _is_ignored(self, relative_path: str) -> tuple[bool, str]:
        basename = os.path.basename(relative_path)
        ext = os.path.splitext(basename)[1].lower()
        
        # Ignore hidden files and directories
        if any(part.startswith('.') and part != '.' for part in relative_path.split(os.sep)):
            return True, "HIDDEN_FILE_OR_DIR"
            
        if any(ignored in relative_path.split(os.sep) for ignored in self.ignored_dirs):
            return True, "VENDOR_OR_BUILD_DIR"
            
        if ext in self.ignored_extensions:
            return True, "BINARY_OR_ARCHIVE"
            
        if basename in self.ignored_files:
            return True, "LOCKFILE"
            
        # Likely secrets heuristic
        lower_base = basename.lower()
        if any(sec in lower_base for sec in self.secret_keywords) or ext in ['.pem', '.key', '.cert']:
            return True, "LIKELY_SECRET"
            
        # .aegisignore
        if any(ign in relative_path for ign in self.aegis_ignore):
            return True, "AEGISIGNORE"
            
        # simple .gitignore substring matching (real gitignore parsing is more complex, but this is a heuristic)
        if any(ign in relative_path for ign in self.git_ignore if not ign.startswith('*')):
            return True, "GITIGNORE"
            
        # Check size budget
        full_path = os.path.join(self.repo_dir, relative_path)
        if os.path.exists(full_path):
            if os.path.getsize(full_path) > self.budgets["max_file_bytes"]:
                return True, "FILE_TOO_LARGE"
                
        return False, ""

    def get_scan_targets(self, changed_files: list = None) -> list:
        """
        Returns a list of safe, relevant files to scan. 
        If changed_files is provided (PR mode), only scans those.
        Otherwise, scans the repo up to the max_files budget.
        """
        targets = []
        
        if changed_files:
            print("[Aegis - Repo Scanner] PR Diff mode: Scanning only changed files.")
            files_to_check = changed_files
        else:
            print("[Aegis - Repo Scanner] Full repo mode.")
            files_to_check = []
            for root, _, files in os.walk(self.repo_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), self.repo_dir)
                    files_to_check.append(rel)
                    
        skipped = {}
        for rel_path in files_to_check:
            ignored, reason = self._is_ignored(rel_path)
            if ignored:
                skipped[rel_path] = reason
                continue
                
            abs_path = os.path.abspath(os.path.join(self.repo_dir, rel_path))
            if os.path.exists(abs_path):
                targets.append(abs_path)
                
            if len(targets) >= self.budgets["max_files"]:
                print(f"[Aegis - Repo Scanner] WARNING: Reached max_files budget ({self.budgets['max_files']}). Truncating scan targets.")
                break
                
        if skipped:
            print(f"[Aegis - Repo Scanner] Skipped {len(skipped)} files. Example reasons:")
            for k, v in list(skipped.items())[:5]:
                print(f"  - {k} ({v})")
                
        return targets
