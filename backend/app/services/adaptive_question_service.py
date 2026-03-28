from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Answer, GameSession, Player, Question
from .progression_service import compute_session_metrics, recommend_difficulty


@dataclass(frozen=True)
class NextQuestionDecision:
    session_id: int
    course_id: int
    player_id: int
    player_level: int
    recommended_difficulty: str
    question: Question | None
    remaining_total: int
    remaining_in_recommended: int


_ORDER = ("easy", "medium", "hard")


class AdaptiveQuestionServiceError(Exception):
    pass


def decide_next_question(db: Session, *, session_id: int) -> NextQuestionDecision:
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session:
        raise AdaptiveQuestionServiceError("Session not found.")

    player = db.query(Player).filter(Player.id == session.player_id).first()
    if not player:
        raise AdaptiveQuestionServiceError("Player not found for session.")

    level = int(getattr(player, "game_level", 1) or 1)
    accuracy, avg_time_ms, emotion = compute_session_metrics(db, session_id=session_id)
    recommended = recommend_difficulty(
        level_number=level,
        accuracy=float(accuracy),
        avg_time_ms=avg_time_ms,
        emotion=emotion,
    )

    answered_ids = select(Answer.question_id).where(Answer.session_id == session_id)

    remaining_total = (
        db.query(Question)
        .filter(Question.course_id == session.course_id)
        .filter(~Question.id.in_(answered_ids))
        .count()
    )

    question = _pick_next_question(
        db,
        course_id=int(session.course_id),
        answered_ids=answered_ids,
        recommended=recommended,
    )

    remaining_in_rec = (
        db.query(Question)
        .filter(Question.course_id == session.course_id)
        .filter(Question.difficulty_level.ilike(recommended))
        .filter(~Question.id.in_(answered_ids))
        .count()
    )

    return NextQuestionDecision(
        session_id=int(session.id),
        course_id=int(session.course_id),
        player_id=int(session.player_id),
        player_level=level,
        recommended_difficulty=recommended,
        question=question,
        remaining_total=int(remaining_total),
        remaining_in_recommended=int(remaining_in_rec),
    )


def list_next_questions(
    db: Session,
    *,
    session_id: int,
    limit: int = 20,
) -> tuple[str, list[Question]]:
    """
    Deterministic question batch for Unity.
    - No randomness.
    - Excludes questions already answered in the session.
    - Primary filter: recommended difficulty for the *current session state*.
    """
    decision = decide_next_question(db, session_id=session_id)
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session:
        raise AdaptiveQuestionServiceError("Session not found.")

    answered_ids = select(Answer.question_id).where(Answer.session_id == session_id)
    course_id = int(session.course_id)

    diffs = _fallback_difficulties(decision.recommended_difficulty)
    out: list[Question] = []
    for diff in diffs:
        rows = (
            db.query(Question)
            .filter(Question.course_id == course_id)
            .filter(Question.difficulty_level.ilike(diff))
            .filter(~Question.id.in_(answered_ids))
            .order_by(Question.id.asc())
            .limit(max(0, int(limit) - len(out)))
            .all()
        )
        out.extend(rows)
        if len(out) >= int(limit):
            break

    return decision.recommended_difficulty, out


def _fallback_difficulties(recommended: str) -> list[str]:
    r = (recommended or "").strip().lower()
    if r not in _ORDER:
        r = "medium"
    if r == "easy":
        return ["easy", "medium", "hard"]
    if r == "hard":
        return ["hard", "medium", "easy"]
    return ["medium", "easy", "hard"]


def _pick_next_question(db: Session, *, course_id: int, answered_ids, recommended: str) -> Question | None:
    diffs = _fallback_difficulties(recommended)
    for diff in diffs:
        q = (
            db.query(Question)
            .filter(Question.course_id == course_id)
            .filter(Question.difficulty_level.ilike(diff))
            .filter(~Question.id.in_(answered_ids))
            .order_by(Question.id.asc())
            .first()
        )
        if q is not None:
            return q
    return None
