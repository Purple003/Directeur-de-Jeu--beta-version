from datetime import datetime, timezone
import logging

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Answer, EmotionEvent, GameSession, LevelProgress, Question
from .progression_service import ProgressionServiceError, update_progression_for_session
from .xapi_service import (
    build_answered_statement,
    build_completed_statement,
    build_started_statement,
    build_level_statement,
    store_statement,
    try_send_to_lrs,
)

logger = logging.getLogger(__name__)


class GameServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = int(status_code)


def start_session(db: Session, *, player_id: int, course_id: int) -> GameSession:
    try:
        session = GameSession(player_id=player_id, course_id=course_id)
        db.add(session)
        db.commit()
        db.refresh(session)

        # Best-effort xAPI (must not block session creation).
        try:
            statement = build_started_statement(player_id=player_id, course_id=course_id, session_id=session.id)
            row = store_statement(db, statement, session_id=session.id)
            if try_send_to_lrs(statement):
                row.sent = True
            db.commit()
        except Exception as exc:
            logger.warning("start_session: xAPI store/send failed (non-blocking): %s", exc)
            try:
                db.rollback()
            except Exception:
                pass

        return session
    except IntegrityError as exc:
        db.rollback()
        # Likely invalid FK (player/course missing)
        raise GameServiceError("Invalid player_id or course_id.", status_code=400) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise GameServiceError("Failed to start session.", status_code=500) from exc


def submit_answer(
    db: Session,
    *,
    session_id: int,
    question_id: int,
    selected_answer: str,
    time_spent_ms: int | None,
    emotion: str | None,
    confidence: float | None,
) -> bool:
    try:
        session = db.query(GameSession).filter(GameSession.id == session_id).first()
        if not session:
            raise GameServiceError("Session not found.", status_code=404)

        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise GameServiceError("Question not found.", status_code=404)
        if question.course_id != session.course_id:
            raise GameServiceError("Question does not belong to this session course.", status_code=400)

        is_correct = _is_correct_answer(question, selected_answer)
        course_id = int(session.course_id)
        player_id = int(session.player_id)

        try:
            # 1) Critical: store the answer. This must succeed for gameplay.
            db.add(
                Answer(
                    session_id=session_id,
                    question_id=question_id,
                    selected_answer=selected_answer,
                    is_correct=is_correct,
                    time_spent_ms=time_spent_ms,
                    emotion=emotion if emotion else None,
                    emotion_confidence=float(confidence) if confidence is not None else None,
                )
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise GameServiceError("Invalid session_id or question_id.", status_code=400) from exc
        except SQLAlchemyError as exc:
            db.rollback()
            raise GameServiceError("Failed to submit answer.", status_code=500) from exc

        # 2) Non-critical: store emotion + xAPI (best-effort, must never break gameplay).
        try:
            if emotion and confidence is not None:
                db.add(
                    EmotionEvent(
                        session_id=session_id,
                        question_id=question_id,
                        emotion=emotion,
                        confidence=float(confidence),
                    )
                )

            statement = build_answered_statement(
                player_id=player_id,
                course_id=course_id,
                question_id=question_id,
                success=is_correct,
                session_id=session_id,
            )
            row = store_statement(db, statement, session_id=session_id)
            if try_send_to_lrs(statement):
                row.sent = True

            db.commit()
        except Exception as exc:
            logger.warning("submit_answer: emotion/xAPI store/send failed (non-blocking): %s", exc)
            try:
                db.rollback()
            except Exception:
                pass

        return bool(is_correct)
    except GameServiceError:
        raise
    except IntegrityError as exc:
        db.rollback()
        raise GameServiceError("Invalid session_id or question_id.", status_code=400) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise GameServiceError("Failed to submit answer.", status_code=500) from exc


def end_session(
    db: Session, *, session_id: int, final_score: float | None
) -> tuple[GameSession, int | None, int | None, str | None]:
    """
    Marks a session as ended, stores final score + duration, and emits xAPI completed.
    Returns (session, duration_ms).
    """
    try:
        # Lock the session row to make idempotency robust under fast double-calls.
        session = (
            db.query(GameSession)
            .filter(GameSession.id == session_id)
            .with_for_update()
            .first()
        )
        if not session:
            raise GameServiceError("Session not found.", status_code=404)

        # Idempotency: if the session is already ended, return the stored values and avoid
        # double progression updates / duplicate xAPI statements.
        if session.ended_at is not None:
            next_level: int | None = None
            recommended: str | None = None
            try:
                lp = (
                    db.query(LevelProgress)
                    .filter(LevelProgress.session_id == session_id)
                    .order_by(LevelProgress.id.desc())
                    .first()
                )
                if lp is not None:
                    next_level = int(lp.level_number) if lp.level_number is not None else None
                    recommended = lp.recommended_difficulty
            except Exception:
                next_level, recommended = None, None
            # Release any row locks acquired by `with_for_update()`.
            try:
                db.rollback()
            except Exception:
                pass
            return session, getattr(session, "duration_ms", None), next_level, recommended

        ended_at = session.ended_at or datetime.now(timezone.utc)

        # Compute score automatically from stored answers (percent 0..100).
        total = db.query(Answer).filter(Answer.session_id == session_id).count()
        correct = (
            db.query(Answer)
            .filter(Answer.session_id == session_id)
            .filter(Answer.is_correct.is_(True))
            .count()
        )
        final_score = float((correct / total) * 100.0) if total else 0.0
        duration_ms: int | None = None
        try:
            if session.started_at:
                duration_ms = int(max(0.0, (ended_at - session.started_at).total_seconds()) * 1000.0)
        except Exception:
            duration_ms = None

        next_level: int | None = None
        recommended: str | None = None
        passed_level: bool | None = None
        level_number_for_statement: int | None = None

        # 1) Critical: persist session end + progression. One commit for the gameplay result.
        try:
            # Update session fields (columns may be added via compatibility migration).
            session.ended_at = ended_at
            session.final_score = float(final_score)
            session.duration_ms = duration_ms

            try:
                current_level, next_level, recommended, passed_level = update_progression_for_session(
                    db,
                    player_id=session.player_id,
                    course_id=session.course_id,
                    session_id=session.id,
                )
                level_number_for_statement = current_level
            except ProgressionServiceError:
                next_level, recommended = None, None

            db.commit()
        except Exception as exc:
            db.rollback()
            raise GameServiceError("Failed to end session.", status_code=500) from exc

        # 2) Non-critical: xAPI statements (best-effort, must never break end-session).
        try:
            statement = build_completed_statement(
                player_id=session.player_id,
                course_id=session.course_id,
                session_id=session.id,
                score=float(final_score),
            )
            row = store_statement(db, statement, session_id=session.id)
            if try_send_to_lrs(statement):
                row.sent = True

            # xAPI: level passed/failed (best-effort).
            if level_number_for_statement is not None and passed_level is not None:
                lvl_stmt = build_level_statement(
                    player_id=session.player_id,
                    course_id=session.course_id,
                    level_number=int(level_number_for_statement),
                    success=bool(passed_level),
                    session_id=session.id,
                )
                lvl_row = store_statement(db, lvl_stmt, session_id=session.id)
                if try_send_to_lrs(lvl_stmt):
                    lvl_row.sent = True

            db.commit()
        except Exception as exc:
            logger.warning("end_session: xAPI store/send failed (non-blocking): %s", exc)
            try:
                db.rollback()
            except Exception:
                pass

        db.refresh(session)
        return session, duration_ms, next_level, recommended
    except GameServiceError:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise GameServiceError("Failed to end session.", status_code=500) from exc


def _is_correct_answer(question: Question, selected_answer: str) -> bool:
    correct = (question.correct_answer or "").strip()
    selected = (selected_answer or "").strip()
    if not correct or not selected:
        return False

    letters = {"A", "B", "C", "D"}
    if correct.upper() in letters:
        if selected.upper() in letters:
            return selected.upper() == correct.upper()

        # Selected is likely the full choice text; map to letter.
        try:
            idx = list(question.choices_json).index(selected)
            mapped = chr(ord("A") + idx)
            return mapped == correct.upper()
        except Exception:
            return False

    # Correct answer stored as the actual string.
    return selected.strip().lower() == correct.strip().lower()
