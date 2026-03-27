import logging
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import env
from ..models import User

logger = logging.getLogger(__name__)


class AuthServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = int(status_code)


_PWD_CONTEXT = None


def create_user(db: Session, *, username: str, password: str, role: str) -> User:
    username = username.strip()
    role = role.strip().lower()
    if role not in ("professor", "student"):
        raise AuthServiceError("Invalid role.")
    if not username:
        raise AuthServiceError("Username is required.")
    if not password or len(password) < 6:
        raise AuthServiceError("Password must be at least 6 characters.")

    # For production: bcrypt is required.
    ctx = _get_pwd_context()
    if ctx is None:
        raise AuthServiceError("Hashing dependency missing: install passlib[bcrypt].", status_code=500)

    salt_b64 = ""
    hash_b64 = _hash_password_bcrypt(password)

    try:
        user = User(username=username, password_salt=salt_b64, password_hash=hash_b64, role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        # Unique username constraint
        raise AuthServiceError("Username already exists.", status_code=409) from exc
    except OperationalError as exc:
        db.rollback()
        raise AuthServiceError("Database connection error.", status_code=503) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("create_user failed: %s", exc)
        msg = "Unable to create user."
        low = str(exc).lower()
        if "does not exist" in low and "users" in low:
            msg = "Database schema mismatch: users table is missing. Run migrations / restart backend to create tables."
        raise AuthServiceError(msg, status_code=500) from exc


def authenticate(db: Session, *, username: str, password: str) -> User:
    username = username.strip()
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise AuthServiceError("Invalid credentials.", status_code=401)

    if not _verify_password(password, user.password_salt, user.password_hash):
        raise AuthServiceError("Invalid credentials.", status_code=401)

    return user


def create_access_token(*, user: User) -> str:
    secret = _get_jwt_secret()
    algorithm = env("JWT_ALGORITHM", "HS256")
    expire_minutes = int(env("JWT_EXPIRE_MINUTES", "60") or "60")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expire_minutes)).timestamp()),
    }
    return _jwt_encode(payload, secret=secret, algorithm=str(algorithm))


def decode_access_token(token: str) -> dict:
    try:
        secret = _get_jwt_secret()
        algorithm = env("JWT_ALGORITHM", "HS256")
        return _jwt_decode(token, secret=secret, algorithm=str(algorithm))
    except AuthServiceError:
        raise
    except Exception as exc:
        raise AuthServiceError("Invalid token.", status_code=401) from exc


def _get_jwt_secret() -> str:
    secret = (env("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        raise AuthServiceError(
            "JWT_SECRET is missing or too short. Set JWT_SECRET in backend/.env (min 32 chars).",
            status_code=500,
        )
    return secret


def _hash_password_bcrypt(password: str) -> str:
    ctx = _get_pwd_context()
    if ctx is None:
        raise AuthServiceError("passlib[bcrypt] is not installed.")
    return ctx.hash(password)


def _hash_password_pbkdf2(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return _b64(salt), _b64(dk)


def _verify_password(password: str, salt_b64: str, hash_b64: str) -> bool:
    # New format: bcrypt in password_hash.
    if (hash_b64 or "").startswith("$2"):
        ctx = _get_pwd_context()
        if ctx is None:
            return False
        try:
            return bool(ctx.verify(password, hash_b64))
        except Exception:
            return False

    # Legacy format: PBKDF2 with base64 salt + base64 hash.
    try:
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(dk, expected)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _get_pwd_context():
    global _PWD_CONTEXT
    if _PWD_CONTEXT is not None:
        return _PWD_CONTEXT
    try:
        from passlib.context import CryptContext  # type: ignore

        _PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return _PWD_CONTEXT
    except Exception:
        return None


def _jwt_encode(payload: dict, *, secret: str, algorithm: str) -> str:
    # Prefer python-jose (requested); fall back to PyJWT if present.
    try:
        from jose import jwt as jose_jwt  # type: ignore

        return jose_jwt.encode(payload, secret, algorithm=algorithm)
    except Exception:
        try:
            import jwt as pyjwt  # type: ignore

            return pyjwt.encode(payload, secret, algorithm=algorithm)
        except Exception as exc:
            raise AuthServiceError("JWT library is missing (install python-jose[cryptography]).") from exc


def _jwt_decode(token: str, *, secret: str, algorithm: str) -> dict:
    try:
        from jose import jwt as jose_jwt  # type: ignore

        return jose_jwt.decode(token, secret, algorithms=[algorithm])
    except Exception:
        try:
            import jwt as pyjwt  # type: ignore

            return pyjwt.decode(token, secret, algorithms=[algorithm])
        except Exception as exc:
            raise AuthServiceError("JWT library is missing (install python-jose[cryptography]).") from exc
