"""Settings, read once at startup from the environment and .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from season.adapters.system import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Settings:
    home: Path
    db_path: Path
    host: str
    port: int
    typesafe_api_key: str | None
    typesafe_model: str
    context: str | None
    min_probability: float

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset({self.base_url, f"http://localhost:{self.port}"})


def load_settings(home: Path | None = None) -> Settings:
    home = Path(home or os.environ.get("SEASON_HOME") or PROJECT_ROOT)
    load_dotenv(home / ".env")
    return Settings(
        home=home,
        db_path=Path(os.environ.get("SEASON_DB") or home / "season.db"),
        host="127.0.0.1",
        port=int(os.environ.get("SEASON_PORT", "8765")),
        typesafe_api_key=(os.environ.get("TYPESAFE_API_KEY") or "").strip() or None,
        typesafe_model=os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"),
        context=(os.environ.get("SEASON_CONTEXT") or "").strip() or None,
        min_probability=float(os.environ.get("SEASON_MIN_PROBABILITY", "0.5")),
    )
