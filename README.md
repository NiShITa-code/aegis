# 🛡️ Aegis — Multi-Agent AI Code Security Platform

> **A Red Team agent finds the vulnerability. A sandboxed Docker environment confirms it's real. A Blue Team agent patches it. Automatically.**

Aegis is an open-source, locally-run AI security pipeline that closes the loop between vulnerability *detection* and *remediation* — powered by any LLM (Gemini, GPT-4, Claude) via [LiteLLM](https://github.com/BerriAI/litellm).

Most security tools tell you *what* is broken. Aegis tells you *and* fixes it, with proof.

---

## How It Works

```
Your Code
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AEGIS PIPELINE                              │
│                                                                 │
│  Phase 1: RED TEAM       Phase 2: SANDBOX        Phase 3: BLUE TEAM  │
│  ┌──────────────┐        ┌─────────────┐         ┌─────────────┐     │
│  │ LLM scans    │──────▶ │ Docker runs │──────▶  │ LLM writes  │     │
│  │ codebase for │        │ exploit to  │         │ secure patch │     │
│  │ CVEs + writes│        │ verify it's │         │ + validates  │     │
│  │ exploit code │        │ real        │         │ the fix      │     │
│  └──────────────┘        └─────────────┘         └─────────────┘     │
│                                                                 │
│  Phase 4: VALIDATION — Sandbox re-runs exploit against patched code  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
secure_app.py  (patched, validated output)
```

**The key insight:** Most LLM security tools skip the sandbox. Aegis actually *runs* the generated exploit in an isolated Docker container to confirm the vulnerability exists before wasting time patching phantom issues. If the exploit fails, Aegis reports the app as secure and stops.

---

## Features

- **Red Team Agent** — Analyzes your entire codebase context (not just one file) and generates structured exploit code with CVE classification and severity rating (CRITICAL / HIGH / MEDIUM / LOW)
- **Sandboxed Verification** — Exploits run in an ephemeral Docker container with `--network none` and a 15-second hard timeout. No network access. Container destroyed after each run.
- **Blue Team Agent** — Reads both the vulnerable code and the confirmed exploit to generate a targeted, minimal patch with a confidence score (1–100)
- **Fix Validation** — The same exploit is run against the patched code to confirm the vulnerability is actually closed
- **Full Codebase Context** — A RAG-like context engine loads your entire repository before analysis, so the agents understand the full architecture, not just the file being targeted
- **CI/CD Integration** — Includes a FastAPI GitHub webhook server that triggers the full pipeline automatically on every pull request
- **Multi-Model Support** — Swap between Gemini, GPT-4, Claude, or any LiteLLM-compatible model via a single env variable

---

## Quick Start

### Prerequisites

- Python 3.10+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- An API key for at least one LLM provider (Gemini, OpenAI, or Anthropic)

### Installation

```bash
# 1. Clone the repo
git clone https://github.com/NiShITa-code/aegis.git
cd aegis/aegis_core

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your API key (choose one)
export GEMINI_API_KEY=your_key_here
# export OPENAI_API_KEY=your_key_here
# export ANTHROPIC_API_KEY=your_key_here

# 4. Run Aegis on the included vulnerable demo app
python orchestrator.py vuln_app.py
```

### What You'll See

```
==================================================
🛡️ WELCOME TO AEGIS: THE GOD-MODE AI APPSEC PLATFORM 🛡️
==================================================
Targeting Codebase: vuln_app.py

--- PHASE 1: RED TEAM ATTACK ---
[Aegis - Context Engine] Scanning repository...
[Aegis - Red Team Agent] Analyzing target code strictly...
[Aegis - Red Team Agent] 🕵️ Vulnerability Found: SQL Injection (CRITICAL)
[Aegis - Red Team Agent] 🎯 Structured exploit generated and saved.

--- PHASE 2: EXPLOIT VERIFICATION ---
[Aegis - Sandbox Judge] 🐳 Spinning up secure Docker container...
[Aegis - Sandbox Judge] 🔴 VULNERABILITY CONFIRMED: The exploit was successful.

--- PHASE 3: BLUE TEAM REMEDIATION ---
[Aegis - Blue Team Agent] 🛠️ Fix Plan: Replaced string interpolation with parameterized queries
[Aegis - Blue Team Agent] 📈 Confidence Score: 97/100
[Aegis - Blue Team Agent] 🛡️ Secure refactoring complete!

--- PHASE 4: VALIDATING THE FIX ---
✅ SUCCESS: The refactored code successfully blocked the exploit!
✅ Secure code saved to: vuln_app_secure.py
==================================================
```

### Run on Your Own Code

```bash
python orchestrator.py path/to/your_app.py
```

---

## CI/CD Integration (GitHub Webhook)

Aegis includes a webhook server that automatically triggers the pipeline on every pull request.

```bash
# Start the webhook server
python server.py

# Aegis listens on http://0.0.0.0:8000/github-webhook
# Configure this URL in your GitHub repo:
# Settings → Webhooks → Add webhook → Content type: application/json
# Events: Pull requests
```

When a PR is opened, updated, or reopened, Aegis automatically runs the full Red→Sandbox→Blue→Validate pipeline and logs the results.

---

## Configuration

Copy `.env.example` to `.env` and set your preferences:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `AEGIS_MODEL` | `gemini/gemini-1.5-pro` | LLM model to use (any LiteLLM-compatible model) |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic Claude API key |

**Switching models:**
```bash
# Use GPT-4o
export AEGIS_MODEL=gpt-4o

# Use Claude
export AEGIS_MODEL=anthropic/claude-opus-4-6

# Use any other LiteLLM-supported model
export AEGIS_MODEL=ollama/codellama  # local model, no API key needed
```

---

## Project Structure

```
aegis_core/
├── orchestrator.py      # Main pipeline — runs all 4 phases in sequence
├── agent_red.py         # Red Team agent — vulnerability detection + exploit generation
├── agent_blue.py        # Blue Team agent — secure patch generation
├── sandbox.py           # Docker-isolated exploit execution + validation
├── context_loader.py    # RAG-like codebase context loader
├── server.py            # FastAPI GitHub webhook server for CI/CD
├── vuln_app.py          # Demo: intentionally vulnerable app (SQL injection)
└── requirements.txt     # Python dependencies
```

---

## Supported Vulnerability Types

Aegis is model-agnostic and will identify any vulnerability the underlying LLM can reason about. Tested with:

- **SQL Injection** (included demo)
- Command Injection
- Path Traversal
- Insecure Deserialization
- Hardcoded Credentials
- Broken Authentication Logic

---

## Security & Safety

Aegis is designed for **authorized security testing only**:

- All exploits run inside Docker containers with `--network none` (zero internet access)
- Containers are destroyed immediately after execution (`--rm` flag)
- Hard 15-second timeout kills any runaway exploit
- Aegis never auto-submits patches — you review the generated `*_secure.py` file before using it
- Never run Aegis on code you don't own or have explicit permission to test

---

## Roadmap

- [ ] Multi-language support (JavaScript/TypeScript, Go, Java)
- [ ] GitHub Actions integration (run as a workflow, not just a webhook)
- [ ] Batch scanning of entire repositories
- [ ] Structured JSON report output
- [ ] Support for OWASP Top 10 benchmark evaluation
- [ ] Web UI dashboard

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Background

Aegis was built as part of AI security research at Imperial College London, alongside work on adversarial LLM testing ([QD-Bandit](https://github.com/NiShITa-code/Research_QDBandit)) and a co-authored paper on LLM red-teaming ([Red-Bandit, arXiv:2510.07239](https://arxiv.org/abs/2510.07239)).

The core insight driving Aegis is that existing static analysis tools produce too many false positives, and LLM-based tools that don't verify exploits dynamically can't be trusted. By combining LLM reasoning with sandboxed dynamic execution, Aegis only flags vulnerabilities it can prove are real.

---

## License

Aegis is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

- Free for personal use, research, and open-source projects
- Free for companies using it internally (not as a service)
- If you offer Aegis as a hosted/commercial service, you must either
  open-source your entire stack (AGPL requirement) or obtain a
  commercial license

**Commercial licensing:** nishita0502@gmail.com

## Citation

If you use Aegis in research, please cite:

```bibtex
@software{aegis2025,
  author = {Jain, Nishita},
  title = {Aegis: Multi-Agent AI Code Security Platform},
  year = {2025},
  url = {https://github.com/NiShITa-code/aegis},
  license = {MIT}
}
```
