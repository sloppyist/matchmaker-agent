"""Configuration management for Matchmaker Agent."""

from enum import Enum
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    OPENROUTER = "openrouter"
    LOCAL = "local"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Provider
    llm_provider: LLMProvider = Field(default=LLMProvider.OPENROUTER)

    # OpenRouter
    openrouter_api_key: Optional[str] = Field(default=None)
    openrouter_model: str = Field(default="anthropic/claude-3-5-haiku-20241022")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")

    # Local LLM
    local_llm_url: str = Field(default="http://localhost:11434/v1")
    local_llm_model: str = Field(default="llama3.2")

    # Database
    database_url: str = Field(
        default="postgresql://matchmaker:matchmaker@localhost:5432/matchmaker_db"
    )

    # Telegram
    telegram_bot_token: Optional[str] = Field(default=None)

    # WhatsApp (Twilio)
    twilio_account_sid: Optional[str] = Field(default=None)
    twilio_auth_token: Optional[str] = Field(default=None)
    twilio_whatsapp_from: str = Field(default="whatsapp:+14155238886")

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # Embedding model for RAG
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384)

    @property
    def active_llm_base_url(self) -> str:
        """Get the base URL for the active LLM provider."""
        if self.llm_provider == LLMProvider.LOCAL:
            return self.local_llm_url
        return self.openrouter_base_url

    @property
    def active_llm_model(self) -> str:
        """Get the model name for the active LLM provider."""
        if self.llm_provider == LLMProvider.LOCAL:
            return self.local_llm_model
        return self.openrouter_model

    @property
    def active_llm_api_key(self) -> Optional[str]:
        """Get the API key for the active LLM provider."""
        if self.llm_provider == LLMProvider.LOCAL:
            return "not-needed"
        return self.openrouter_api_key


settings = Settings()
