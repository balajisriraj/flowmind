from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration from the environment (prefix ``FLOWMIND_``) or ``.env``."""

    model_config = SettingsConfigDict(env_prefix="FLOWMIND_", env_file=".env", extra="ignore")

    llm: str = "anthropic"  # "anthropic" or "scripted"
    model: str = "claude-opus-5-5"
    scripted_delay: float = 0.0
    analyse_effort: str = "medium"
    design_effort: str = "medium"
    step_effort: str = "low"
    max_fixes: int = 3

    data_dir: Path = ROOT / "data"
    fixtures: Path = ROOT / "fixtures"
    # How often the runner checks schedules and watched folders.
    tick_seconds: float = 2.0
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def workspace(self) -> Path:
        return self.data_dir / "workspace"


@lru_cache
def get_settings() -> Settings:
    return Settings()
