from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import User
from .auth_service import AuthServiceError, decode_access_token


def get_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.cookies.get("asg_token")


def get_current_user(request: Request) -> User:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    try:
        payload = decode_access_token(token)
    except AuthServiceError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    user_id = int(payload.get("sub") or 0)
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
        return user
    finally:
        db.close()


def try_get_current_user(request: Request) -> User | None:
    """
    Best-effort auth for endpoints that should work without auth (e.g. Unity prototypes)
    but can optionally attach ownership when a professor token is present.
    """
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def require_role(role: str):
    def _dep(request: Request) -> User:
        user = get_current_user(request)
        if user.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        return user

    return _dep
