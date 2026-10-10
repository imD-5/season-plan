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
    extra_origins: tuple[str, ...] = ()

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def allowed_origins(self) -> frozenset[str]:
        """Pages allowed to write. Add more (e.g. a Tailscale HTTPS address for your phone) with
        SEASON_ALLOWED_ORIGINS in .env, comma-separated."""
        return frozenset({self.base_url, f"http://localhost:{self.port}", *self.extra_origins})


def _origins(raw: str) -> tuple[str, ...]:
    """"https://mac.tail1234.ts.net, https://x" -> ("https://mac.tail1234.ts.net", "https://x").
    Origins are scheme://host[:port] with no path, so trailing slashes are dropped."""
    out = []
    for item in raw.split(","):
        item = item.strip().rstrip("/")
        if not item:
            continue
        if not item.startswith(("http://", "https://")) or "/" in item.split("://", 1)[1]:
            raise ValueError(f"SEASON_ALLOWED_ORIGINS: {item!r} is not an origin like https://host")
        out.append(item)
    return tuple(out)


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
        extra_origins=_origins(os.environ.get("SEASON_ALLOWED_ORIGINS", "")),
    )
