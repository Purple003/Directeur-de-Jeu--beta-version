import os
import secrets
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402


def main() -> None:
    # Ensure we have a JWT secret for login tests (fallback only; prefer backend/.env).
    os.environ.setdefault("JWT_SECRET", "dev_" + secrets.token_hex(24))

    username = f"smoke_{secrets.token_hex(4)}"
    password = "Passw0rd!"

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200, r.text

        r = client.post(
            "/auth/register",
            json={"username": username, "password": password, "role": "student"},
        )
        assert r.status_code == 201, r.text
        user_id = r.json()["data"]["user_id"]
        assert isinstance(user_id, int)

        r = client.post("/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        token = r.json()["data"]["access_token"]
        assert token and isinstance(token, str)

    print("smoke_auth: OK")


if __name__ == "__main__":
    main()
