"""Paths, environment and settings for the research agent."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


def load_env(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env loader - does not override variables already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()


class Settings:
    """Runtime settings sourced from environment variables (.env)."""

    def __init__(self) -> None:
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self.gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.search_provider = os.environ.get("SEARCH_PROVIDER", "ddg")
        self.github_token = os.environ.get("GITHUB_TOKEN", "")

    @property
    def has_llm_key(self) -> bool:
        return bool(self.gemini_api_key)

    # canonical output locations
    canonical_db = DATA_DIR / "apps.json"
    cache_dir = DATA_DIR / "cache"
    runs_dir = DATA_DIR / "runs"
    audit_dir = DATA_DIR / "audit"
    charts_dir = DATA_DIR / "charts"
    site_dir = DATA_DIR / "site"


SETTINGS = Settings()
