import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        r = client.post("/emotion/analyze", json={"session_id": "1", "emotion_hint": "happy", "store": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] in ("calm", "engaged", "stressed"), body
        assert 0.0 <= float(body["confidence"]) <= 1.0, body

    print("smoke_emotion_state: OK")


if __name__ == "__main__":
    main()

