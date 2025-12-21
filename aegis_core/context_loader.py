import os
import glob
import ast

def jaccard_similarity(str1: str, str2: str) -> float:
    a = set(str1.lower().split())
    b = set(str2.lower().split())
    if not a or not b: return 0.0
    return len(a.intersection(b)) / len(a.union(b))

def extract_local_imports(target_filepath: str, repo_directory: str) -> list[str]:
    """Uses Native Python AST to find direct file dependencies."""
    try:
        with open(target_filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=target_filepath)
            
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
                    
        # Convert imports to local file paths
        local_files = []
        for imp in imports:
            potential_file = os.path.join(repo_directory, f"{imp}.py")
            if os.path.exists(potential_file):
                local_files.append(os.path.abspath(potential_file))
        return local_files
    except Exception as e:
        print(f"[Aegis - AST Engine] Failed to parse AST for {target_filepath}: {e}")
        return []

def load_codebase_context(directory: str = ".", ignore_dirs=None, target_code_path: str = None) -> str:
    """
    Scans the directory for Python files and concatenates them to build architecture context.
    This simulates a RAG (Retrieval-Augmented Generation) pipeline for the LLM.
    """
    if ignore_dirs is None:
        ignore_dirs = ['venv', '__pycache__', '.git', 'node_modules', '.idea']
        
    ignore_files_list = []
    aegisignore_path = os.path.join(directory, '.aegisignore')
    if os.path.exists(aegisignore_path):
        with open(aegisignore_path, 'r', encoding='utf-8') as f:
            ignore_files_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
    context_blocks = []
    MAX_FILE_SIZE = 1024 * 1024 # 1 MB completely ignores
    MAX_TOTAL_SIZE = 50000 # 50KB heuristic
    
    target_content = ""
    ast_critical_paths = []
    if target_code_path and os.path.exists(target_code_path):
        with open(target_code_path, 'r', encoding='utf-8') as f:
            target_content = f.read()
        if target_code_path.endswith('.py'):
            ast_critical_paths = extract_local_imports(target_code_path, directory)
            if ast_critical_paths:
                print(f"[Aegis - AST Engine] Found {len(ast_critical_paths)} strict AST dependencies.")
            
    print(f"[Aegis - Context Engine] Scanning repository {os.path.abspath(directory)}...")
    
    for root, dirs, files in os.walk(directory):
        # Remove ignored directories from traversal
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for file in files:
            if file.endswith(".py"):
                if file in ignore_files_list:
                    continue
                    
                filepath = os.path.join(root, file)
                if os.path.getsize(filepath) > MAX_FILE_SIZE:
                    continue
                    
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    relative_path = os.path.relpath(filepath, directory)
                    is_ast_critical = os.path.abspath(filepath) in ast_critical_paths
                    context_blocks.append({"path": relative_path, "content": content, "ast_critical": is_ast_critical})
                except Exception as e:
                    print(f"Failed to read {filepath}: {e}")
                    
    if target_content and sum(len(b['content']) for b in context_blocks) > MAX_TOTAL_SIZE:
        print("[Aegis - Context Engine] Context large. Applying Semantic Jaccard Ranking + AST Priority...")
        for b in context_blocks:
            # AST critical files get a huge score boost guarantees inclusion
            base_score = jaccard_similarity(target_content, b['content'])
            b['score'] = base_score + (100.0 if b.get('ast_critical') else 0.0)
            
        context_blocks.sort(key=lambda x: x['score'], reverse=True)
        
        limited_blocks = []
        current_size = 0
        for b in context_blocks:
            if current_size + len(b['content']) > MAX_TOTAL_SIZE and len(limited_blocks) >= 3:
                break
            limited_blocks.append(b)
            current_size += len(b['content'])
            
        context_blocks = limited_blocks
        
    full_context = "\n".join([f"--- FILE: {b['path']} ---\n{b['content']}\n" for b in context_blocks])
    print(f"[Aegis - Context Engine] Loaded {len(context_blocks)} files into Context memory.")
    return full_context

if __name__ == "__main__":
    ctx = load_codebase_context()
    print(f"Context size: {len(ctx)} characters.")
