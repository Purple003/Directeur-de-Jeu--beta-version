from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Ensure `backend/` is on sys.path so `import app` works when running from `backend/scripts/`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _try_import(name: str) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(name)
        ver = getattr(mod, "__version__", None)
        return True, f"{name} OK" + (f" ({ver})" if ver else "")
    except Exception as exc:
        return False, f"{name} MISSING/ERROR: {exc}"


def main() -> int:
    print("=== Backend Doctor ===")
    print("python:", sys.version.split()[0])
    print("exe   :", sys.executable)

    required = ["fastapi", "uvicorn", "sqlalchemy", "requests"]
    optional = ["cv2", "mediapipe", "deepface"]

    print("\n[Required imports]")
    ok = True
    for name in required:
        success, msg = _try_import(name)
        ok = ok and success
        print("-", msg)

    print("\n[Optional emotion imports]")
    for name in optional:
        success, msg = _try_import(name)
        print("-", msg)

    print("\n[DB connectivity]")
    try:
        from app.database import engine

        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        safe = engine.url.render_as_string(hide_password=True)
        print("-", "DB OK:", safe)
    except Exception as exc:
        ok = False
        print("-", "DB ERROR:", exc)

    print("\n[App import]")
    try:
        from app.main import app

        print("-", "FastAPI OK:", app.title, app.version)
    except Exception as exc:
        ok = False
        print("-", "FastAPI import ERROR:", exc)

    print("\nResult:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
