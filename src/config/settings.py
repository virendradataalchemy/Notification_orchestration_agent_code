from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra='ignore')

    # Application
    app_name: str = "notification-orchestration-app"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    api_version: str = "v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    # Database
    database_url: str
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # Redis
    redis_url: str
    redis_max_connections: int = 50

    # Security
    secret_key: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 15
    api_key_expiration_days: int = 90
    allow_public_tenant_signup: bool = True
    admin_username: str = "admin"
    admin_password: Optional[str] = None  # Falls back to secret_key when not set
    admin_session_hours: int = 8

    # Rate Limiting
    rate_limit_per_user_hour: int = 100
    rate_limit_per_app_minute: int = 10000
    rate_limit_system_minute: int = 1000000

    # AWS Services
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # AWS SES
    aws_ses_region: str = "us-east-1"
    aws_ses_from_email: str
    aws_ses_rate_limit: int = 14

    # AWS SQS
    sqs_email_queue_url: Optional[str] = None
    sqs_sms_queue_url: Optional[str] = None
    sqs_whatsapp_queue_url: Optional[str] = None
    sqs_slack_queue_url: Optional[str] = None
    sqs_push_queue_url: Optional[str] = None
    sqs_voice_queue_url: Optional[str] = None
    sqs_inapp_queue_url: Optional[str] = None

    # AWS S3
    s3_bucket_name: Optional[str] = None
    s3_attachments_prefix: str = "attachments/"
    s3_templates_prefix: str = "templates/"

    # Twilio
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    twilio_whatsapp_number: Optional[str] = None

    # Azure
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None

    # Mailgun
    mailgun_api_key: Optional[str] = None
    mailgun_domain: Optional[str] = None
    mailgun_from_email: Optional[str] = None
    mailgun_base_url: str = "https://api.mailgun.net/v3"

    # Slack
    slack_bot_token: Optional[str] = None
    slack_signing_secret: Optional[str] = None
    slack_webhook_url: Optional[str] = None

    slack_access_token: Optional[str] = None
    slack_refresh_token: Optional[str] = None

    slack_channel_id: Optional[str] = None

    # Firebase
    firebase_credentials_path: Optional[str] = None
    firebase_project_id: Optional[str] = None
    firebase_public_key: Optional[str] = None
    firebase_private_key: Optional[str] = None

    # Apple Push Notifications
    apns_key_id: Optional[str] = None
    apns_team_id: Optional[str] = None
    apns_bundle_id: Optional[str] = None
    apns_key_path: Optional[str] = None
    apns_use_sandbox: bool = True

    # ElevenLabs
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None

    # LLM
    qwen_api_key: Optional[str] = None
    qwen_model: str = "qwen-2.5-72b"
    qwen_model_id: str = "qwen.qwen3-next-80b-a3b"
    mistral_api_key: Optional[str] = None

    # Monitoring
    sentry_dsn: Optional[str] = None
    prometheus_port: int = 9090

    # Features
    enable_deduplication: bool = True
    enable_scheduled_delivery: bool = True
    enable_analytics: bool = True
    enable_audit_logging: bool = True

    # Testing/Mock Mode
    use_mock_providers: bool = False  # Set to True to use mock providers for testing

    # Deduplication
    dedup_ttl_seconds: int = 600
    dedup_content_hash_ttl: int = 300
    dedup_user_per_type_limit: int = 1

    # Retry
    retry_max_attempts: int = 3
    retry_exponential_base: int = 2
    retry_initial_delay_seconds: int = 30
    retry_max_delay_seconds: int = 1800

    # Retention
    notification_content_retention_days: int = 90
    audit_log_hot_retention_days: int = 30
    audit_log_warm_retention_days: int = 365

    @property
    def api_prefix(self) -> str:
        """Get API prefix with version."""
        return f"/api/{self.api_version}"

    @property
    def cors_origins(self) -> list[str]:
        """Get CORS allowed origins."""
        if self.app_env == "development":
            return ["*"]
        return [
            "https://yourdomain.com",
            "https://app.yourdomain.com",
        ]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
