import os
import yaml

def get_functional_test_command(repo_path: str) -> str:
    """
    Determines the functional test command to run.
    1. Checks aegis.yml or aegis.test.yml for a 'test_command' key.
    2. Falls back to smart defaults based on the project structure.
    3. Returns None if no command is found.
    """
    config_files = ["aegis.yml", "aegis.test.yml", "aegis.yaml"]
    for conf in config_files:
        conf_path = os.path.join(repo_path, conf)
        if os.path.exists(conf_path):
            try:
                with open(conf_path, 'r') as f:
                    data = yaml.safe_load(f)
                    if data and isinstance(data, dict) and 'test_command' in data:
                        return data['test_command']
            except Exception as e:
                print(f"[Aegis - Config] Warning: Failed to parse {conf}: {e}")

    # Smart Defaults
    if os.path.exists(os.path.join(repo_path, "pytest.ini")) or os.path.exists(os.path.join(repo_path, "tests")):
        if os.path.exists(os.path.join(repo_path, "requirements.txt")) or os.path.exists(os.path.join(repo_path, "pyproject.toml")):
            return "pytest"
    
    if os.path.exists(os.path.join(repo_path, "package.json")):
        return "npm test"
        
    if os.path.exists(os.path.join(repo_path, "go.mod")):
        return "go test ./..."
        
    if os.path.exists(os.path.join(repo_path, "Cargo.toml")):
        return "cargo test"

    return None

def get_aegis_budgets(repo_path: str) -> dict:
    """
    Retrieves the budget settings for Aegis to prevent cost explosion and unbounded scans.
    """
    # Default sensible budgets
    budgets = {
        "max_files": 100,
        "max_file_bytes": 1024 * 500, # 500 KB per file max
        "max_total_bytes": 1024 * 1024 * 5, # 5 MB total context max
        "max_context_tokens": 50000,
        "max_vulnerabilities": 5,
        "max_llm_calls": 20,
        "max_runtime": 900 # 15 minutes
    }
    
    config_files = ["aegis.yml", "aegis.yaml"]
    for conf in config_files:
        conf_path = os.path.join(repo_path, conf)
        if os.path.exists(conf_path):
            try:
                with open(conf_path, 'r') as f:
                    data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        b = data.get("budgets", {})
                        if isinstance(b, dict):
                            budgets.update({k: v for k, v in b.items() if k in budgets})
            except Exception as e:
                print(f"[Aegis - Config] Warning: Failed to parse {conf} for budgets: {e}")
                
    return budgets
