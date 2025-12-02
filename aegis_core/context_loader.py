import os
import glob

def load_codebase_context(directory: str = ".", ignore_dirs=None) -> str:
    """
    Scans the directory for Python files and concatenates them to build
    architecture context for the LLM agents.
    """
    if ignore_dirs is None:
        ignore_dirs = ['venv', '__pycache__', '.git', 'node_modules', '.idea']

    context_blocks = []
    print(f"[Aegis - Context Engine] Scanning repository {os.path.abspath(directory)}...")

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    relative_path = os.path.relpath(filepath, directory)
                    context_blocks.append({"path": relative_path, "content": content})
                except Exception as e:
                    print(f"Failed to read {filepath}: {e}")

    full_context = "\n".join([f"--- FILE: {b['path']} ---\n{b['content']}\n" for b in context_blocks])
    print(f"[Aegis - Context Engine] Loaded {len(context_blocks)} files into context memory.")
    return full_context
