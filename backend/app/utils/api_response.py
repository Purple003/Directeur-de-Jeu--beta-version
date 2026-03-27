from typing import Any

# Standard API envelope used across Unity/game clients.


def ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def fail(message: str, *, details: Any = None) -> dict:
    return {"success": False, "data": None, "error": {"message": message, "details": details}}
