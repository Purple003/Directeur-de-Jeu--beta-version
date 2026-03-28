"""
Emotion persistence + xAPI side-effects.

Vision inference lives in `app.emotion_analysis` (MediaPipe + DeepFace + fusion).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..emotion_analysis import AnalysisResult, EmotionOrchestrator
from ..models import EmotionEvent, GameSession
from .xapi_service import build_emotion_statement, store_statement, try_send_to_lrs

logger = logging.getLogger(__name__)


class EmotionServiceError(Exception):
    pass


_ORCHESTRATOR: EmotionOrchestrator | None = None


def get_orchestrator() -> EmotionOrchestrator:
    """Process-wide singleton so DeepFace's worker pool and caches are reused."""
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = EmotionOrchestrator()
    return _ORCHESTRATOR


def analyze_emotion_detailed(
    *, emotion_hint: str | None = None, image_bytes: bytes | None = None
) -> AnalysisResult:
    """
    Full bridge output for /emotion/analyze-detailed (stress, engagement, boredom, scores).
    Must never raise — returns neutral fusion on hard failures.
    """
    try:
        return get_orchestrator().analyze_bytes(image_bytes, emotion_hint=emotion_hint)
    except Exception as exc:  # pragma: no cover
        logger.exception("[Emotion] analyze_emotion_detailed failure: %s", exc)
        from ..emotion_analysis.models.signals import LandmarkMetrics
        from ..emotion_analysis.services.fusion import fuse_signals_safe

        return fuse_signals_safe(
            mp=LandmarkMetrics(),
            df=None,
            heuristic_emotion="neutral",
            heuristic_confidence=0.5,
        )


def analyze_emotion(
    *, emotion_hint: str | None = None, image_bytes: bytes | None = None
) -> tuple[str, float]:
    """
    Backward-compatible (emotion, confidence) for callers that only need the label.
    """
    out = analyze_emotion_detailed(emotion_hint=emotion_hint, image_bytes=image_bytes)
    return out.emotion, float(out.confidence)


def store_emotion(
    db: Session,
    *,
    session_id: int,
    question_id: int | None,
    emotion: str,
    confidence: float,
) -> None:
    """
    Stores an emotion event and *optionally* emits xAPI.

    IMPORTANT: This function must NEVER break the main API flow.
    - No `db.begin()` (SQLAlchemy 2.0+ autobegin makes nested begin() crash).
    - On any failure: log + rollback + return.
    """
    try:
        db.add(
            EmotionEvent(
                session_id=session_id,
                question_id=question_id,
                emotion=emotion,
                confidence=float(confidence),
            )
        )
        db.commit()
    except Exception as exc:
        logger.exception("store_emotion failed (non-blocking): %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return

    try:
        session = db.query(GameSession).filter(GameSession.id == session_id).first()
        if not session:
            return

        statement = build_emotion_statement(
            player_id=session.player_id,
            course_id=session.course_id,
            session_id=session_id,
            emotion=emotion,
            confidence=float(confidence),
        )
        row = store_statement(db, statement, session_id=session_id)
        sent = try_send_to_lrs(statement)
        if sent:
            row.sent = True
        db.commit()
    except Exception as exc:
        logger.warning("store_emotion: xAPI store/send failed (non-blocking): %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return
