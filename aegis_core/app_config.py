import os
import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, model_validator
from typing import Optional, Dict, Any, List

class TenantConfig(BaseSettings):
    api_key: SecretStr
    repos: List[str]

    model_config = SettingsConfigDict(extra="ignore")

class AegisSettings(BaseSettings):
    aegis_env: str = "production"
    github_app_id: Optional[str] = None
    github_app_private_key: Optional[SecretStr] = None
    github_token: Optional[SecretStr] = None
    
    # Reports configuration
    reports_dir: str = ".aegis_reports"
    report_retention_days: int = 30
    
    # Worker configuration
    max_concurrent_workers: int = 5
    worker_timeout_seconds: int = 1800  # 30 mins
    
    # Rate limiting
    max_requests_per_repo_per_hour: int = 10

    # Tenant config (JSON string mapped to Dict)
    aegis_tenant_config: Optional[str] = None
    tenant_config: Dict[str, TenantConfig] = {}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @model_validator(mode="after")
    def validate_and_parse(self) -> "AegisSettings":
        if self.aegis_env.lower() not in ["development", "production", "test"]:
            raise ValueError(f"AEGIS_ENV must be one of ['development', 'production', 'test']")
        self.aegis_env = self.aegis_env.lower()
        
        if self.aegis_tenant_config:
            try:
                parsed = json.loads(self.aegis_tenant_config)
                self.tenant_config = {
                    tenant: TenantConfig(**config) for tenant, config in parsed.items()
                }
            except Exception as e:
                raise ValueError(f"Invalid AEGIS_TENANT_CONFIG JSON: {e}")
        return self

    def is_production(self) -> bool:
        return self.aegis_env == "production"

    def get_tenant_for_repo(self, repo_full_name: str) -> Optional[str]:
        for tenant, config in self.tenant_config.items():
            if repo_full_name in config.repos or "*" in config.repos:
                return tenant
        return None

# Global settings instance
settings = AegisSettings()
