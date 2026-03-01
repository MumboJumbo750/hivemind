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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.hivemind_cors_origins.split(",")]


settings = Settings()
