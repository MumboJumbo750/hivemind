import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://hivemind:hivemind@postgres:5432/hivemind"
    database_url_sync: str = "postgresql+psycopg2://hivemind:hivemind@postgres:5432/hivemind"

    hivemind_mode: str = "solo"
    hivemind_token_budget: int = 8000
    hivemind_routing_threshold: float = 0.85
    hivemind_dlq_max_attempts: int = 5
    audit_retention_days: int = 90
    audit_row_deletion_days: int = 180
    hivemind_cors_origins: str = "http://localhost:5173"
    hivemind_prompt_minify: bool = True
    testing: bool = False

    hivemind_node_name: str = "hivemind-node"
    hivemind_node_url: str = "http://localhost:8000"
    hivemind_key_passphrase: str = ""
    hivemind_federation_enabled: bool = False
    hivemind_peers_config: str = "./peers.yaml"
    hivemind_federation_topology: str = "direct_mesh"
    hivemind_hive_station_url: str = ""
    hivemind_hive_station_token: str = ""
    hivemind_hive_relay_enabled: bool = False
    hivemind_transport: str = "sse"  # SSE always active; "stdio" adds local stdio loop
    hivemind_mcp_api_key: str = "hivemind-local-key"

    # Ollama / Embedding settings (Phase 3)
    hivemind_ollama_url: str = "http://ollama:11434"
    hivemind_embedding_model: str = "nomic-embed-text"
    hivemind_embedding_batch_size: int = 50
    hivemind_embedding_cb_threshold: int = 3
    hivemind_embedding_cb_backoff_base: int = 60
    hivemind_embedding_cb_backoff_max: int = 600
    hivemind_prompt_history_retention_days: int = 180

    # Webhook secrets
    hivemind_youtrack_webhook_secret: str = ""
    hivemind_sentry_webhook_secret: str = ""
    hivemind_youtrack_url: str = ""
    hivemind_youtrack_token: str = ""
    hivemind_sentry_token: str = ""
    hivemind_youtrack_state_mapping: str = ""

    hivemind_outbox_interval: int = 30
    hivemind_heartbeat_interval: int = 300
    hivemind_peer_timeout: int = 900
    hivemind_federation_ping_interval: int = 60
    hivemind_federation_offline_threshold: int = 3

    # Phase 6 — SLA & Notification settings
    hivemind_sla_cron_interval: int = 3600  # seconds, default 1h
    notification_retention_days: int = 90
    notification_unread_retention_days: int = 365

    jwt_secret_key: str = "changeme-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Sentry
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 1.0

    # Phase 8 — AI Provider settings
    hivemind_ai_api_key: str = ""
    hivemind_ai_rpm_limit: int = 10
    hivemind_ai_tpm_limit: int = 0  # 0 = no limit
    hivemind_token_count_calibration: str = ""  # JSON: {"anthropic": 1.05, ...}

    # Phase 8 — GitHub integration
    hivemind_github_webhook_secret: str = ""
    hivemind_github_token: str = ""
    hivemind_github_url: str = "https://api.github.com"

    # Phase 8 — GitLab integration
    hivemind_gitlab_webhook_secret: str = ""
    hivemind_gitlab_token: str = ""
    hivemind_gitlab_url: str = "https://gitlab.com"

    # Phase 8 — Conductor settings
    hivemind_conductor_enabled: bool = False
    hivemind_conductor_parallel: int = 3
    hivemind_conductor_cooldown_seconds: int = 10
    hivemind_conductor_ide_timeout: int = 300
    hivemind_conductor_ide_timeout_seconds: int = 300  # deprecated alias

    # Phase 8 — Governance & TLS
    hivemind_enforce_tls: bool = False
    hivemind_auto_review_grace_minutes: int = 30

    # Filesystem Tools (TASK-WFS-002)
    hivemind_workspace_root: str = "/workspace"
    hivemind_fs_deny_list: str = ".git/objects,.env,.env.local,.env.production"
    hivemind_fs_rate_limit: int = 60  # max calls per tool per minute

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.hivemind_cors_origins.split(",")]

    @property
    def conductor_ide_timeout_seconds(self) -> int:
        """Return IDE timeout in seconds (prefers HIVEMIND_CONDUCTOR_IDE_TIMEOUT)."""
        value = self.hivemind_conductor_ide_timeout or self.hivemind_conductor_ide_timeout_seconds
        return max(int(value), 1)


settings = Settings()


def has_routing_threshold_env_override() -> bool:
    """Return True when HIVEMIND_ROUTING_THRESHOLD is explicitly set."""
    value = os.getenv("HIVEMIND_ROUTING_THRESHOLD")
    return value is not None and value.strip() != ""
