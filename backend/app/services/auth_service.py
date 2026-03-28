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


_PWD_MARKER_SHA256 = "v2_sha256"


def create_user(db: Session, *, username: str, password: str, role: str) -> User:
    username = username.strip()
    role = role.strip().lower()
    if role not in ("professor", "student"):
        raise AuthServiceError("Invalid role.")
    if not username:
        raise AuthServiceError("Username is required.")
    if not password or len(password) < 6:
        raise AuthServiceError("Password must be at least 6 characters.")

    # Default format: PBKDF2-HMAC-SHA256 (pure stdlib, works on all Pythons / OSes).
    # This avoids passlib+bcrypt compatibility issues on newer Python versions.
    try:
        salt_b64, hash_b64 = _hash_password_pbkdf2(password)
    except Exception as exc:
        raise AuthServiceError("Invalid password.", status_code=400) from exc

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

    # Opportunistic migration: if the user is still on legacy bcrypt(prehash) format,
    # upgrade to PBKDF2 so future logins do not depend on bcrypt/passlib.
    if (user.password_salt or "") == _PWD_MARKER_SHA256 and (user.password_hash or "").startswith("$2"):
        try:
            salt_b64, hash_b64 = _hash_password_pbkdf2(password)
            user.password_salt = salt_b64
            user.password_hash = hash_b64
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()

    return user


def create_access_token(*, user: User) -> str:
    secret = _get_jwt_secret()
    algorithm = env("JWT_ALGORITHM", "HS256")
    # Backward-compatible env keys (some setups use ACCESS_TOKEN_EXPIRE_MINUTES).
    raw_exp = env("JWT_EXPIRE_MINUTES") or env("ACCESS_TOKEN_EXPIRE_MINUTES") or "60"
    expire_minutes = int(str(raw_exp).strip() or "60")
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
        # Surface token-expired errors explicitly (helps debugging during long-running flows).
        try:
            from jose.exceptions import ExpiredSignatureError  # type: ignore

            if isinstance(exc, ExpiredSignatureError):
                raise AuthServiceError("Token expired.", status_code=401) from exc
        except Exception:
            pass

        raise AuthServiceError("Invalid token.", status_code=401) from exc


def _get_jwt_secret() -> str:
    secret = (env("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        raise AuthServiceError(
            "JWT_SECRET is missing or too short. Set JWT_SECRET in backend/.env (min 32 chars).",
            status_code=500,
        )
    return secret


def _hash_password_pbkdf2(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return _b64(salt), _b64(dk)


def _verify_password(password: str, salt_b64: str, hash_b64: str) -> bool:
    # Legacy format (v2): bcrypt hash of a SHA-256 pre-hash (stored marker in password_salt).
    # We verify with bcrypt directly to avoid passlib backend issues.
    if (salt_b64 or "") == _PWD_MARKER_SHA256 and (hash_b64 or "").startswith("$2"):
        try:
            import bcrypt  # type: ignore

            secret = _prehash_password(password).encode("utf-8")
            return bool(bcrypt.checkpw(secret, (hash_b64 or "").encode("utf-8")))
        except Exception:
            return False

    # Other passlib-style hashes (start with "$") are not supported unless migrated.
    if (hash_b64 or "").startswith("$"):
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


def _prehash_password(password: str) -> str:
    """
    Used only to verify the legacy v2 bcrypt format.
    """
    digest = hashlib.sha256((password or "").encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")

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
