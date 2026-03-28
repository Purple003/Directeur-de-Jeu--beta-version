import json
import os
import secrets
from urllib.parse import urlencode

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
COURSE_ID = int(os.getenv("COURSE_ID", "57"))


def _pretty(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _api_ok(resp_json: dict) -> dict:
    if not isinstance(resp_json, dict) or not resp_json.get("success"):
        raise RuntimeError(f"API error: {_pretty(resp_json)}")
    return resp_json.get("data") or {}


def _login_professor_token() -> str:
    token = (os.getenv("PROF_TOKEN") or "").strip()
    if token:
        return token

    username = (os.getenv("PROF_USERNAME") or "").strip()
    password = (os.getenv("PROF_PASSWORD") or "").strip()
    if not username or not password:
        raise SystemExit(
            "Set PROF_TOKEN or (PROF_USERNAME and PROF_PASSWORD) env vars to call /dashboard/api endpoints."
        )

    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    data = _api_ok(r.json())
    return str(data["access_token"])


def main() -> None:
    # 1) Create a player and start a session for the course, so storing emotions works (FK constraints).
    player_name = "smoke_player_" + secrets.token_hex(4)
    r = requests.post(f"{BASE_URL}/player/create", json={"name": player_name, "age": 18}, timeout=20)
    player_data = _api_ok(r.json())
    player_id = int(player_data["player_id"])

    r = requests.post(
        f"{BASE_URL}/game/start-session",
        json={"player_id": player_id, "course_id": COURSE_ID},
        timeout=20,
    )
    session_data = _api_ok(r.json())
    session_id = int(session_data["session_id"])

    # 2) Store an emotion event (state endpoint).
    r = requests.post(
        f"{BASE_URL}/emotion/analyze",
        json={"session_id": str(session_id), "emotion_hint": "happy", "store": True},
        timeout=30,
    )
    analyze_body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
    print("POST /emotion/analyze")
    print("HTTP", r.status_code)
    print(_pretty(analyze_body))

    # 3) Fetch dashboard summary and print latest emotion for the session.
    token = _login_professor_token()
    auth_headers = {"Authorization": f"Bearer {token}"}
    qs = urlencode({"session_id": session_id})
    url = f"{BASE_URL}/dashboard/api/course/{COURSE_ID}/emotion-summary?{qs}"
    r = requests.get(url, headers=auth_headers, timeout=20)
    print("\nGET /dashboard/api/course/{}/emotion-summary".format(COURSE_ID))
    print("HTTP", r.status_code)
    if r.status_code != 200:
        raise RuntimeError(
            "GET emotion-summary failed: HTTP {} {}\n"
            "- Ensure PROF_* credentials are for a professor.\n"
            "- Ensure COURSE_ID exists and is owned by that professor.\n".format(r.status_code, r.text)
        )
    body = r.json()
    print(_pretty(body))

    data = _api_ok(body)
    latest_for_session = data.get("latest_for_session")
    print("\nLatest emotion for session_id={}:".format(session_id))
    print(_pretty(latest_for_session))


if __name__ == "__main__":
    main()
