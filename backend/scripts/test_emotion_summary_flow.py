import json
import os
import secrets
import time
from urllib.parse import urlencode

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
COURSE_ID = int(os.getenv("COURSE_ID", "57"))
WAIT_SECONDS = int(os.getenv("WAIT_SECONDS", "61"))  # default aligns with server throttle (60s)


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
        raise SystemExit("Set PROF_TOKEN or (PROF_USERNAME and PROF_PASSWORD) env vars.")

    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    data = _api_ok(r.json())
    return str(data["access_token"])


def _post_emotion(session_id: int, emotion_hint: str) -> dict:
    r = requests.post(
        f"{BASE_URL}/emotion/analyze",
        json={"session_id": str(session_id), "emotion_hint": emotion_hint, "store": True},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"POST /emotion/analyze failed: HTTP {r.status_code} {r.text}")
    body = r.json()
    if not isinstance(body, dict) or "state" not in body:
        raise RuntimeError(f"Unexpected /emotion/analyze response: {_pretty(body)}")
    return body


def main() -> None:
    # 1) Prepare a real session_id (create player + start session for the course).
    player_name = "flow_player_" + secrets.token_hex(4)
    r = requests.post(f"{BASE_URL}/player/create", json={"name": player_name, "age": 18}, timeout=20)
    player_id = int(_api_ok(r.json())["player_id"])

    r = requests.post(
        f"{BASE_URL}/game/start-session",
        json={"player_id": player_id, "course_id": COURSE_ID},
        timeout=20,
    )
    session_id = int(_api_ok(r.json())["session_id"])

    # 2) POST happy (store=true)
    happy = _post_emotion(session_id, "happy")
    print("POST /emotion/analyze (happy)")
    print(_pretty(happy))

    # 3) Wait for server throttle window, then POST sad (store=true)
    if WAIT_SECONDS > 0:
        print(f"\nWaiting {WAIT_SECONDS}s to bypass server throttle...")
        time.sleep(WAIT_SECONDS)

    sad = _post_emotion(session_id, "sad")
    print("\nPOST /emotion/analyze (sad)")
    print(_pretty(sad))

    # 4) GET dashboard summary and read latest emotion for this session_id
    token = _login_professor_token()
    auth_headers = {"Authorization": f"Bearer {token}"}
    qs = urlencode({"session_id": session_id})
    url = f"{BASE_URL}/dashboard/api/course/{COURSE_ID}/emotion-summary?{qs}"
    r = requests.get(url, headers=auth_headers, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(
            "GET emotion-summary failed: HTTP {} {}\n"
            "- Ensure the backend is running.\n"
            "- Ensure PROF_* credentials are for a professor.\n"
            "- Ensure COURSE_ID exists and is owned by that professor.\n".format(r.status_code, r.text)
        )
    summary_env = r.json()
    summary = _api_ok(summary_env)
    latest_for_session = summary.get("latest_for_session")
    print("\nGET /dashboard/api/course/{}/emotion-summary?session_id={}".format(COURSE_ID, session_id))
    print(_pretty(latest_for_session))

    # 5) Verify "sad" => stressed is reflected in the summary
    if not isinstance(latest_for_session, dict):
        raise RuntimeError(f"latest_for_session missing/unexpected: {_pretty(summary_env)}")

    latest_state = str(latest_for_session.get("emotion") or "")
    if latest_state != "stressed":
        raise RuntimeError(f"Expected latest emotion state 'stressed', got '{latest_state}'")

    print("\nVERIFY OK: latest emotion state is 'stressed'.")


if __name__ == "__main__":
    main()
