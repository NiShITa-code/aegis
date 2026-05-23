import os
import json
import re
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from logger import log

class OrchestratorArtifact(BaseModel):
    target_file: str
    status: str
    sandbox_output: str
    original_code: str
    exploit_code: str
    patched_code: str
    functional_test_result: Optional[str] = None
    llm_calls: int = 0
    token_usage: Dict[str, int] = Field(default_factory=dict)
    duration_seconds: float = 0.0

class ScanReport(BaseModel):
    scan_id: str
    timestamp: str
    duration_seconds: float
    repo_metadata: Dict[str, Any]
    scan_targets: List[str]
    skipped_files: Dict[str, str]
    sast_summary: Dict[str, Any]
    budget_usage: Dict[str, Any]
    orchestrator_results: List[OrchestratorArtifact]
    final_status: str
    github_write_action: Optional[str] = None

class AegisReporter:
    def __init__(self, scan_id: str):
        self.scan_id = scan_id
        self.start_time = datetime.now()
        self.repo_metadata = {}
        self.scan_targets = []
        self.skipped_files = {}
        self.sast_summary = {}
        self.budget_usage = {
            "total_llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
        self.orchestrator_results = []
        self.final_status = "UNKNOWN"
        self.github_write_action = None
        self.reports_dir = ".aegis_reports"
        os.makedirs(self.reports_dir, exist_ok=True)
        
    def add_orchestrator_artifact(self, artifact: OrchestratorArtifact):
        self.orchestrator_results.append(artifact)
        self.budget_usage["total_llm_calls"] += artifact.llm_calls
        if artifact.token_usage:
            self.budget_usage["prompt_tokens"] += artifact.token_usage.get("prompt_tokens", 0)
            self.budget_usage["completion_tokens"] += artifact.token_usage.get("completion_tokens", 0)
            self.budget_usage["total_tokens"] += artifact.token_usage.get("total_tokens", 0)

    def _redact_sensitive_info(self, text: str) -> str:
        if not text:
            return ""
        
        # Redact common secrets patterns
        text = re.sub(r'(api[_-]?key[\s:=]+)[a-zA-Z0-9_\-]+', r'\1[REDACTED]', text, flags=re.IGNORECASE)
        text = re.sub(r'(secret[\s:=]+)[a-zA-Z0-9_\-]+', r'\1[REDACTED]', text, flags=re.IGNORECASE)
        text = re.sub(r'(token[\s:=]+)[a-zA-Z0-9_\-]+', r'\1[REDACTED]', text, flags=re.IGNORECASE)
        text = re.sub(r'(password[\s:=]+)[a-zA-Z0-9_\-]+', r'\1[REDACTED]', text, flags=re.IGNORECASE)
        
        # Redact generic credentials like sk-xxxx for OpenAI
        text = re.sub(r'sk-[a-zA-Z0-9]{32,}', '[REDACTED_SK]', text)
        text = re.sub(r'ghp_[a-zA-Z0-9]{36}', '[REDACTED_GITHUB_PAT]', text)
        
        return text

    def build_report(self) -> ScanReport:
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if not self.scan_targets:
            if self.final_status == "UNKNOWN":
                self.final_status = "SKIPPED_NO_TARGETS"
        elif self.sast_summary.get("failed"):
            if self.final_status == "UNKNOWN":
                self.final_status = "SAST_FAILED"
        elif not self.orchestrator_results:
            if self.final_status == "UNKNOWN":
                self.final_status = "SECURE_NO_VULNERABILITIES"
        else:
            all_secured = True
            for res in self.orchestrator_results:
                if res.status != "SECURED" and res.status != "NO_VULNERABILITY" and res.status != "DUPLICATE_FINDING":
                    all_secured = False
                    self.final_status = res.status
                    break
            if all_secured and self.final_status == "UNKNOWN":
                self.final_status = "SECURED"

        for res in self.orchestrator_results:
            res.original_code = self._redact_sensitive_info(res.original_code)
            res.patched_code = self._redact_sensitive_info(res.patched_code)
            res.exploit_code = self._redact_sensitive_info(res.exploit_code)
            res.sandbox_output = self._redact_sensitive_info(res.sandbox_output)

        report = ScanReport(
            scan_id=self.scan_id,
            timestamp=self.start_time.isoformat(),
            duration_seconds=duration,
            repo_metadata=self.repo_metadata,
            scan_targets=self.scan_targets,
            skipped_files=self.skipped_files,
            sast_summary=self.sast_summary,
            budget_usage=self.budget_usage,
            orchestrator_results=self.orchestrator_results,
            final_status=self.final_status,
            github_write_action=self.github_write_action
        )
        return report

    def generate_markdown(self, report: ScanReport) -> str:
        md = f"# Aegis Scan Report: {self.scan_id}\n\n"
        md += f"**Final Status:** `{self.final_status}`\n"
        md += f"**Timestamp:** {report.timestamp}\n"
        md += f"**Duration:** {report.duration_seconds:.2f}s\n"
        md += f"**GitHub Action:** {self.github_write_action or 'None'}\n\n"
        
        md += "## Budget & Scale\n"
        md += f"- **Scan Targets:** {len(self.scan_targets)}\n"
        md += f"- **Skipped Files:** {len(self.skipped_files)}\n"
        md += f"- **LLM Calls:** {self.budget_usage['total_llm_calls']}\n"
        md += f"- **Total Tokens:** {self.budget_usage['total_tokens']}\n\n"
        
        if self.skipped_files:
            md += "### Skipped Files\n"
            for f, reason in list(self.skipped_files.items())[:10]:
                md += f"- `{f}`: {reason}\n"
            if len(self.skipped_files) > 10:
                md += f"- *(and {len(self.skipped_files) - 10} more...)*\n\n"
                
        md += "## Findings\n"
        for idx, res in enumerate(self.orchestrator_results):
            md += f"### {idx+1}. {res.target_file} ({res.status})\n"
            md += f"**Sandbox Validation:**\n```\n{res.sandbox_output[:500]}...\n```\n"
            
        return md

    def save(self):
        report = self.build_report()
        
        json_tmp_path = os.path.join(self.reports_dir, f"{self.scan_id}.json.tmp")
        json_final_path = os.path.join(self.reports_dir, f"{self.scan_id}.json")
        
        md_tmp_path = os.path.join(self.reports_dir, f"{self.scan_id}.md.tmp")
        md_final_path = os.path.join(self.reports_dir, f"{self.scan_id}.md")
        
        try:
            with open(json_tmp_path, 'w') as f:
                f.write(report.model_dump_json(indent=2))
            os.replace(json_tmp_path, json_final_path)
            
            with open(md_tmp_path, 'w') as f:
                f.write(self.generate_markdown(report))
            os.replace(md_tmp_path, md_final_path)
            
            log.info(f"Report saved to {json_final_path}")
        except Exception as e:
            log.error(f"Failed to save report: {e}")
            
        return json_final_path, md_final_path
