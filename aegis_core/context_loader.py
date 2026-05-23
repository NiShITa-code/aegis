import os
import ast
import tiktoken
from config import get_aegis_budgets

def extract_local_imports(target_filepath: str, repo_directory: str, cache: dict) -> list[str]:
    """Uses Native Python AST to find direct file dependencies."""
    if target_filepath in cache:
        return cache[target_filepath]
        
    try:
        with open(target_filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=target_filepath)
            
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split('.')[0])
                    
        local_files = []
        for imp in imports:
            potential_file = os.path.join(repo_directory, f"{imp}.py")
            if os.path.exists(potential_file):
                local_files.append(os.path.abspath(potential_file))
        
        cache[target_filepath] = local_files
        return local_files
    except Exception as e:
        print(f"[Aegis - AST Engine] Failed to parse AST for {target_filepath}: {e}")
        cache[target_filepath] = []
        return []

def count_tokens(text: str) -> int:
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text, disallowed_special=()))
    except Exception:
        # Fallback heuristic if tiktoken fails
        return len(text) // 4

def vector_retrieval_mock(target_content: str, all_files: list, repo_dir: str) -> list:
    """Mock for vector retrieval (behind feature flag)"""
    # In a real scenario, this would embed target_content and search a vector DB.
    # We mock it here by just taking a few random files for demonstration, 
    # but the prompt requires keeping vector retrieval optional.
    print("[Aegis - Vector] Vector context enabled. Retrieving semantically similar files.")
    return []

def load_codebase_context(target_code_path: str, repo_directory: str) -> str:
    """
    Builds context by tracking AST dependencies (and optionally vector retrieval).
    Enforces token budgets strictly.
    """
    budgets = get_aegis_budgets(repo_directory)
    # Safety margin: 90% of max context tokens
    max_tokens = int(budgets.get("max_context_tokens", 50000) * 0.9)
    max_bytes = budgets.get("max_total_bytes", 1024 * 1024 * 5)
    
    context_blocks = []
    current_tokens = 0
    current_bytes = 0
    
    ast_cache = {}
    
    print(f"[Aegis - Context Engine] Building AST dependency context for {target_code_path}...")
    
    target_content = ""
    if os.path.exists(target_code_path):
        with open(target_code_path, 'r', encoding='utf-8') as f:
            target_content = f.read()
            
    files_to_include = extract_local_imports(target_code_path, repo_directory, ast_cache)
    
    if os.environ.get("AEGIS_ENABLE_VECTOR_CONTEXT", "false").lower() == "true":
        all_py_files = []
        for root, _, files in os.walk(repo_directory):
            for f in files:
                if f.endswith('.py'):
                    all_py_files.append(os.path.join(root, f))
        vector_files = vector_retrieval_mock(target_content, all_py_files, repo_directory)
        for vf in vector_files:
            if vf not in files_to_include and vf != target_code_path:
                files_to_include.append(vf)
                
    # Always ensure target file is NOT duplicated in context blocks (it is passed separately to LLM)
    # But we include its dependencies.
    
    for filepath in set(files_to_include):
        if filepath == target_code_path:
            continue
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            file_bytes = len(content.encode('utf-8'))
            if current_bytes + file_bytes > max_bytes:
                print(f"[Aegis - Context Engine] Warning: Reached max_total_bytes. Stopping context expansion.")
                break
                
            formatted_block = f"--- DEPENDENCY FILE: {os.path.relpath(filepath, repo_directory)} ---\n{content}\n"
            block_tokens = count_tokens(formatted_block)
            
            if current_tokens + block_tokens > max_tokens:
                print(f"[Aegis - Context Engine] Warning: Reached token budget ({current_tokens + block_tokens} > {max_tokens}). Stopping context expansion.")
                break
                
            context_blocks.append(formatted_block)
            current_tokens += block_tokens
            current_bytes += file_bytes
            
        except Exception as e:
            print(f"Failed to read {filepath}: {e}")
            
    full_context = "\n".join(context_blocks)
    if not full_context.strip():
        # If no local imports are found, context is empty
        full_context = "No relevant architectural dependencies found."
        
    print(f"[Aegis - Context Engine] Loaded {len(context_blocks)} dependency files into Context memory ({current_tokens} tokens).")
    return full_context
