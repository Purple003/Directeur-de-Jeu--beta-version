import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ApiResponse
from ..schemas_auth import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse
from ..services.auth_service import AuthServiceError, authenticate, create_access_token, create_user
from ..utils.api_response import ok

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=ApiResponse[RegisterResponse], status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        user = create_user(db, username=payload.username, password=payload.password, role=payload.role)
    except AuthServiceError as exc:
        logger.warning("auth.register failed: %s (status=%s)", str(exc), exc.status_code)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("auth.register unhandled error")
        raise HTTPException(status_code=500, detail="Internal server error.")

    return ok(RegisterResponse(message="User created", user_id=user.id, role=user.role).model_dump())


@router.post("/login", response_model=ApiResponse[LoginResponse], status_code=status.HTTP_200_OK)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = authenticate(db, username=payload.username, password=payload.password)
        token = create_access_token(user=user)
    except AuthServiceError as exc:
        msg = str(exc)
        logger.warning("auth.login failed: %s (status=%s)", msg, exc.status_code)
        raise HTTPException(status_code=exc.status_code, detail=msg)
    except Exception:
        logger.exception("auth.login unhandled error")
        raise HTTPException(status_code=500, detail="Internal server error.")

    return ok(LoginResponse(access_token=token, token_type="bearer", role=user.role).model_dump())
