from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .emotion_service import analyze_emotion_detailed, store_emotion

logger = logging.getLogger(__name__)


_STATE_VALUES = ("calm", "engaged", "stressed")


def map_emotion_to_state(emotion: str | None) -> str:
    e = (emotion or "").strip().lower()
    if e == "happy":
        return "engaged"
    if e == "neutral":
        return "calm"
    if e in ("sad", "fear", "angry"):
        return "stressed"
    # Reasonable defaults for extra DeepFace labels.
    if e in ("disgust",):
        return "stressed"
    if e in ("surprise",):
        return "engaged"
    return "calm"


def decode_image_base64(raw: str) -> bytes:
    s = (raw or "").strip()
    if not s:
        return b""
    # Support data URLs: data:image/jpeg;base64,...
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1].strip()
    # Some clients include whitespace/newlines.
    s = "".join(s.split())
    return base64.b64decode(s, validate=False)


@dataclass(frozen=True)
class CachedEmotionState:
    at_monotonic: float
    state: str
    confidence: float


_CACHE: dict[int, CachedEmotionState] = {}


def _min_interval_s() -> float:
    # Endpoint-level throttle: prevents accidental "continuous detection" even if clients misbehave.
    return float(os.getenv("EMOTION_API_MIN_INTERVAL_S", "60") or "60")


def analyze_emotion_state(
    db: Session,
    *,
    session_id: int,
    question_id: int | None = None,
    image_bytes: bytes | None = None,
    image_base64: str | None = None,
    emotion_hint: str | None = None,
    store: bool = True,
) -> tuple[str, float]:
    """
    Returns (state, confidence) with a 60s default throttle per session.

    - Uses existing fusion pipeline (MediaPipe + optional DeepFace).
    - Maps emotions to a simple gameplay state: calm | engaged | stressed.
    - Stores the *state* as EmotionEvent.emotion when store=True (non-blocking).
    """
    now = time.monotonic()
    cached = _CACHE.get(int(session_id))
    interval = _min_interval_s()
    if cached is not None and interval > 0 and (now - cached.at_monotonic) < interval:
        return cached.state, float(cached.confidence)

    img = image_bytes
    if img is None and image_base64:
        try:
            img = decode_image_base64(image_base64)
        except Exception as exc:
            logger.warning("[EmotionState] base64 decode failed (ignored): %s", exc)
            img = None

    out = analyze_emotion_detailed(emotion_hint=emotion_hint, image_bytes=img)
    state = map_emotion_to_state(out.emotion)
    confidence = max(0.0, min(1.0, float(out.confidence)))
    if state not in _STATE_VALUES:
        state = "calm"

    _CACHE[int(session_id)] = CachedEmotionState(at_monotonic=now, state=state, confidence=confidence)

    if store:
        try:
            store_emotion(db, session_id=int(session_id), question_id=question_id, emotion=state, confidence=confidence)
        except Exception as exc:
            logger.debug("[EmotionState] store ignored: %s", exc)

    return state, confidence

