import os
from typing import Any

import requests
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import XAPIStatement


class XAPIServiceError(Exception):
    pass


def build_answered_statement(
    *,
    player_id: int,
    course_id: int,
    question_id: int,
    success: bool,
    session_id: int | None = None,
) -> dict[str, Any]:
    # Minimal xAPI statement shape (can be extended later with more context and extensions).
    return {
        "actor": {
            "name": f"Player{player_id}",
            "account": {"name": str(player_id), "homePage": "http://adaptive-game.local"},
        },
        "verb": {"id": "http://adlnet.gov/expapi/verbs/answered", "display": {"en-US": "answered"}},
        "object": {"id": f"question_{question_id}"},
        "result": {"success": bool(success)},
        "context": {
            "extensions": {
                "course_id": course_id,
                "player_id": player_id,
                "session_id": session_id,
            }
        },
    }


def build_started_statement(*, player_id: int, course_id: int, session_id: int) -> dict[str, Any]:
    return {
        "actor": {
            "name": f"Player{player_id}",
            "account": {"name": str(player_id), "homePage": "http://adaptive-game.local"},
        },
        "verb": {"id": "http://adlnet.gov/expapi/verbs/initialized", "display": {"en-US": "started"}},
        "object": {"id": f"course_{course_id}"},
        "context": {"extensions": {"course_id": course_id, "player_id": player_id, "session_id": session_id}},
    }


def build_completed_statement(*, player_id: int, course_id: int, session_id: int, score: float) -> dict[str, Any]:
    return {
        "actor": {
            "name": f"Player{player_id}",
            "account": {"name": str(player_id), "homePage": "http://adaptive-game.local"},
        },
        "verb": {"id": "http://adlnet.gov/expapi/verbs/completed", "display": {"en-US": "completed"}},
        "object": {"id": f"course_{course_id}"},
        "result": {"score": {"scaled": max(0.0, min(1.0, score / 100.0))}},
        "context": {"extensions": {"course_id": course_id, "player_id": player_id, "session_id": session_id}},
    }


def build_emotion_statement(
    *, player_id: int, course_id: int, session_id: int, emotion: str, confidence: float
) -> dict[str, Any]:
    return {
        "actor": {
            "name": f"Player{player_id}",
            "account": {"name": str(player_id), "homePage": "http://adaptive-game.local"},
        },
        "verb": {"id": "http://adlnet.gov/expapi/verbs/experienced", "display": {"en-US": "felt"}},
        "object": {"id": "emotion"},
        "result": {"extensions": {"emotion": emotion, "confidence": confidence}},
        "context": {"extensions": {"course_id": course_id, "player_id": player_id, "session_id": session_id}},
    }


def build_level_statement(
    *,
    player_id: int,
    course_id: int,
    level_number: int,
    success: bool,
    session_id: int | None = None,
) -> dict[str, Any]:
    verb = "passed" if success else "failed"
    verb_id = f"http://adlnet.gov/expapi/verbs/{verb}"
    return {
        "actor": {
            "name": f"Player{player_id}",
            "account": {"name": str(player_id), "homePage": "http://adaptive-game.local"},
        },
        "verb": {"id": verb_id, "display": {"en-US": verb}},
        "object": {"id": f"course_{course_id}_level_{level_number}"},
        "result": {"success": bool(success)},
        "context": {"extensions": {"course_id": course_id, "player_id": player_id, "session_id": session_id}},
    }


def store_statement(db: Session, statement: dict[str, Any], *, session_id: int | None) -> XAPIStatement:
    try:
        row = XAPIStatement(session_id=session_id, statement_json=statement, sent=False)
        db.add(row)
        db.flush()
        return row
    except SQLAlchemyError as exc:
        raise XAPIServiceError("Failed to store xAPI statement.") from exc


def try_send_to_lrs(statement: dict[str, Any]) -> bool:
    """
    Best-effort send to an LRS. If not configured, returns False.

    Env vars:
    - LRS_ENDPOINT (e.g. https://lrs.example/xapi/statements)
    - LRS_USERNAME / LRS_PASSWORD (basic auth) OR LRS_AUTH (full Authorization header)
    """
    endpoint = os.getenv("LRS_ENDPOINT", "").strip()
    if not endpoint:
        return False

    headers = {"Content-Type": "application/json"}
    auth_header = os.getenv("LRS_AUTH", "").strip()
    if auth_header:
        headers["Authorization"] = auth_header
        auth = None
    else:
        username = os.getenv("LRS_USERNAME", "").strip()
        password = os.getenv("LRS_PASSWORD", "").strip()
        auth = (username, password) if username and password else None

    try:
        resp = requests.post(endpoint, json=statement, headers=headers, auth=auth, timeout=10)
        return 200 <= resp.status_code < 300
    except requests.RequestException:
        return False
