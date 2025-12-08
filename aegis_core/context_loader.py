import os
import glob

def jaccard_similarity(str1: str, str2: str) -> float:
    a = set(str1.lower().split())
    b = set(str2.lower().split())
    if not a or not b: return 0.0
    return len(a.intersection(b)) / len(a.union(b))

def load_codebase_context(directory: str = ".", ignore_dirs=None, target_code_path: str = None) -> str:
    """
    Scans the directory for Python files and concatenates them to build
    architecture context. Applies Jaccard ranking when context is large.
    """
    if ignore_dirs is None:
        ignore_dirs = ['venv', '__pycache__', '.git', 'node_modules', '.idea']

    context_blocks = []
    MAX_FILE_SIZE = 1024 * 1024  # 1 MB
    MAX_TOTAL_SIZE = 50000       # 50KB heuristic
    print(f"[Aegis - Context Engine] Scanning repository {os.path.abspath(directory)}...")

    target_content = ""
    if target_code_path and os.path.exists(target_code_path):
        with open(target_code_path, 'r', encoding='utf-8') as f:
            target_content = f.read()

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                if os.path.getsize(filepath) > MAX_FILE_SIZE:
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    relative_path = os.path.relpath(filepath, directory)
                    context_blocks.append({"path": relative_path, "content": content})
                except Exception as e:
                    print(f"Failed to read {filepath}: {e}")

    if target_content and sum(len(b['content']) for b in context_blocks) > MAX_TOTAL_SIZE:
        print("[Aegis - Context Engine] Context large. Applying Semantic Jaccard Ranking...")
        for b in context_blocks:
            b['score'] = jaccard_similarity(target_content, b['content'])
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
    print(f"[Aegis - Context Engine] Loaded {len(context_blocks)} files into context memory.")
    return full_context
