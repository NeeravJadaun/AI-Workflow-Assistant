import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def db_path() -> str:
    return os.environ.get("DB_PATH", str(BASE_DIR / "workflow.db"))


def policy_path() -> Path:
    return Path(os.environ.get("POLICY_PATH", BASE_DIR / "data" / "policy.md"))


def openai_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or None


def openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def secret_key() -> str:
    # Set SECRET_KEY in .env for stable sessions across restarts.
    return os.environ.get("SECRET_KEY", "dev-only-insecure-secret")
