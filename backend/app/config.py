import os
from pathlib import Path

from dotenv import dotenv_values

_LOADED = False


def load_env_once() -> None:
    """
    Loads env vars from:
    - DOTENV_PATH (optional)
    - backend/.env
    - repo-root/.env

    Only fills missing/empty vars; does not override non-empty process env.
    """
    global _LOADED
    if _LOADED:
        return

    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = Path(__file__).resolve().parents[1]
    explicit = os.getenv("DOTENV_PATH")

    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(backend_dir / ".env")
    candidates.append(repo_root / ".env")

    for path in candidates:
        if not path.exists():
            continue
        values = dotenv_values(path)
        for key, value in values.items():
            if value is None:
                continue
            current = os.getenv(key)
            if current is None or current == "":
                os.environ[key] = str(value)

    _LOADED = True


def env(key: str, default: str | None = None) -> str | None:
    load_env_once()
    return os.getenv(key, default)

