import os

class SecurityUtilsError(Exception):
    pass

def is_safe_path(base_dir: str, target_path: str) -> bool:
    """
    Checks if a target_path is safely contained within base_dir.
    Rejects absolute paths, path traversal (../), and symlink escapes.
    """
    # 1. Reject absolute paths if they don't explicitly start with base_dir,
    # but generally we expect relative paths from the LLM.
    if os.path.isabs(target_path):
        # We enforce that the LLM only gives relative paths to prevent confusion.
        return False
        
    # 2. Check for path traversal characters
    if ".." in target_path or target_path.startswith("/"):
        return False
        
    # 3. Resolve absolute paths to check for symlink escapes
    abs_base = os.path.abspath(base_dir)
    abs_target = os.path.abspath(os.path.join(base_dir, target_path))
    
    # 4. Enforce that the resolved target is within the resolved base directory
    if not abs_target.startswith(abs_base):
        return False
        
    # 5. Check symlinks (if the path actually exists, we check realpath)
    if os.path.exists(abs_target):
        real_target = os.path.realpath(abs_target)
        if not real_target.startswith(abs_base):
            return False

    return True

def validate_safe_path(base_dir: str, target_path: str):
    if not is_safe_path(base_dir, target_path):
        raise SecurityUtilsError(f"Unsafe path detected: {target_path}")
