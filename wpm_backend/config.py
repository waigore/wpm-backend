"""Application configuration and settings management."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    username: str
    password: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    import_dir: str = "import"
    log_level: str = "INFO"
    log_dir: str = "logs"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

