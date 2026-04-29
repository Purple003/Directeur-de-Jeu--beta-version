from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from ..models import Answer, GameSession, Player, Question
from .llm_service import AdaptedQuestionContent, LLMConfigError, LLMServiceError, adapt_question_presentation
from .progression_service import compute_session_metrics, recommend_difficulty


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NextQuestionDecision:
    session_id: int
    course_id: int
    player_id: int
    player_level: int
    recommended_difficulty: str
    question: Question | None
    adapted_question_text: str | None
    hint: str | None
    tone: str | None
    remaining_total: int
    remaining_in_recommended: int


_ORDER = ("easy", "medium", "hard")


class AdaptiveQuestionServiceError(Exception):
    pass


def decide_next_question(db: Session, *, session_id: int) -> NextQuestionDecision:
    session = (
        db.query(GameSession)
        .filter(GameSession.id == session_id)
        .with_for_update()
        .first()
    )
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

    course_id = int(session.course_id)
    total_questions = (
        db.query(Question)
        .filter(Question.course_id == course_id)
        .count()
    )
    tracked_used_ids = _normalize_question_ids(getattr(session, "used_question_ids", None))
    answered_ids = _load_answered_question_ids(db, session_id=session_id)
    used_ids = _bootstrap_used_question_ids(
        tracked_used_ids=tracked_used_ids,
        answered_ids=answered_ids,
        total_questions=total_questions,
    )

    if used_ids != tracked_used_ids:
        session.used_question_ids = used_ids
        db.flush()

    remaining_before_pick = _count_remaining_questions(
        db,
        course_id=course_id,
        excluded_ids=used_ids,
    )
    reset_applied = False

    if total_questions > 0 and remaining_before_pick == 0:
        logger.info("[Backend] Resetting question pool sessionId=%s courseId=%s", session_id, course_id)
        used_ids = []
        session.used_question_ids = []
        db.flush()
        remaining_before_pick = total_questions
        reset_applied = True

    question = _pick_next_question(
        db,
        course_id=course_id,
        excluded_ids=used_ids,
        recommended=recommended,
        shuffle=reset_applied,
    )

    if question is not None:
        used_ids = [*used_ids, int(question.id)]
        session.used_question_ids = used_ids
        db.commit()
        logger.info("[Backend] Selected questionId=%s sessionId=%s", question.id, session_id)
    else:
        db.commit()
        logger.info("[Backend] Selected questionId=None sessionId=%s", session_id)

    remaining_total = _count_remaining_questions(
        db,
        course_id=course_id,
        excluded_ids=used_ids,
    )
    remaining_in_rec = _count_remaining_questions(
        db,
        course_id=course_id,
        excluded_ids=used_ids,
        difficulty=recommended,
    )

    logger.info("[Backend] Used questions count=%s sessionId=%s", len(used_ids), session_id)
    logger.info("[Backend] Remaining questions=%s sessionId=%s", remaining_total, session_id)

    adapted = _adapt_question_if_needed(
        question=question,
        recommended_difficulty=recommended,
        emotion=emotion,
        accuracy=float(accuracy),
        avg_time_ms=avg_time_ms,
        recent_total=_count_answer_rows(db, session_id=session_id),
    )

    return NextQuestionDecision(
        session_id=int(session.id),
        course_id=course_id,
        player_id=int(session.player_id),
        player_level=level,
        recommended_difficulty=recommended,
        question=question,
        adapted_question_text=adapted.adapted_question_text if adapted else None,
        hint=adapted.hint if adapted else None,
        tone=adapted.tone if adapted else None,
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
    - Excludes questions already served or answered in the session.
    - Primary filter: recommended difficulty for the current session state.
    """
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

    course_id = int(session.course_id)
    answered_ids = _load_answered_question_ids(db, session_id=session_id)
    excluded_ids = _bootstrap_used_question_ids(
        tracked_used_ids=_normalize_question_ids(getattr(session, "used_question_ids", None)),
        answered_ids=answered_ids,
        total_questions=_count_all_questions(db, course_id=course_id),
    )

    diffs = _fallback_difficulties(recommended)
    out: list[Question] = []
    for diff in diffs:
        rows = (
            _build_question_query(
                db,
                course_id=course_id,
                excluded_ids=excluded_ids,
                difficulty=diff,
            )
            .order_by(Question.id.asc())
            .limit(max(0, int(limit) - len(out)))
            .all()
        )
        out.extend(rows)
        if len(out) >= int(limit):
            break

    return recommended, out


def _fallback_difficulties(recommended: str) -> list[str]:
    r = (recommended or "").strip().lower()
    if r not in _ORDER:
        r = "medium"
    if r == "easy":
        return ["easy", "medium", "hard"]
    if r == "hard":
        return ["hard", "medium", "easy"]
    return ["medium", "easy", "hard"]


def _pick_next_question(
    db: Session,
    *,
    course_id: int,
    excluded_ids: list[int],
    recommended: str,
    shuffle: bool,
) -> Question | None:
    diffs = _fallback_difficulties(recommended)
    for diff in diffs:
        q = _build_question_query(
            db,
            course_id=course_id,
            excluded_ids=excluded_ids,
            difficulty=diff,
        )
        if shuffle:
            q = q.order_by(func.random(), Question.id.asc())
        else:
            q = q.order_by(Question.id.asc())
        picked = q.first()
        if picked is not None:
            return picked
    return None


def _count_remaining_questions(
    db: Session,
    *,
    course_id: int,
    excluded_ids: list[int],
    difficulty: str | None = None,
) -> int:
    return int(
        _build_question_query(
            db,
            course_id=course_id,
            excluded_ids=excluded_ids,
            difficulty=difficulty,
        ).count()
    )


def _count_all_questions(db: Session, *, course_id: int) -> int:
    return int(
        db.query(Question)
        .filter(Question.course_id == course_id)
        .count()
    )


def _build_question_query(
    db: Session,
    *,
    course_id: int,
    excluded_ids: list[int],
    difficulty: str | None = None,
) -> Query:
    query = db.query(Question).filter(Question.course_id == course_id)
    if difficulty:
        query = query.filter(Question.difficulty_level.ilike(str(difficulty).strip().lower()))
    if excluded_ids:
        query = query.filter(~Question.id.in_(excluded_ids))
    return query


def _load_answered_question_ids(db: Session, *, session_id: int) -> list[int]:
    rows = (
        db.query(Answer.question_id)
        .filter(Answer.session_id == session_id)
        .distinct()
        .all()
    )
    return [int(row[0]) for row in rows if row and row[0] is not None]


def _count_answer_rows(db: Session, *, session_id: int) -> int:
    return int(
        db.query(Answer)
        .filter(Answer.session_id == session_id)
        .count()
    )


def _normalize_question_ids(raw_ids: object) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in list(raw_ids or []):
        try:
            qid = int(value)
        except (TypeError, ValueError):
            continue
        if qid <= 0 or qid in seen:
            continue
        seen.add(qid)
        out.append(qid)
    return out


def _bootstrap_used_question_ids(
    *,
    tracked_used_ids: list[int],
    answered_ids: list[int],
    total_questions: int,
) -> list[int]:
    if tracked_used_ids:
        return tracked_used_ids
    if 0 < len(answered_ids) < int(total_questions):
        return answered_ids
    return []


def _adapt_question_if_needed(
    *,
    question: Question | None,
    recommended_difficulty: str,
    emotion: str | None,
    accuracy: float,
    avg_time_ms: int | None,
    recent_total: int,
) -> AdaptedQuestionContent | None:
    if question is None:
        return None

    try:
        adapted = adapt_question_presentation(
            question_text=question.question,
            difficulty_level=question.difficulty_level or recommended_difficulty,
            user_emotion=emotion,
            last_performance={
                "accuracy": float(accuracy),
                "avg_time_ms": avg_time_ms,
                "recent_correct": int(round(float(accuracy) * float(recent_total))),
                "recent_total": int(recent_total),
            },
        )
        logger.info(
            "[Backend] AI adapted questionId=%s tone=%s hint=%s",
            question.id,
            adapted.tone,
            bool(adapted.hint),
        )
        return adapted
    except (LLMConfigError, LLMServiceError) as exc:
        logger.warning("[Backend] AI adaptation fallback questionId=%s msg=%s", getattr(question, "id", None), str(exc))
    except Exception:
        logger.exception("[Backend] AI adaptation unhandled questionId=%s", getattr(question, "id", None))

    return AdaptedQuestionContent(
        adapted_question_text=question.question,
        hint=None,
        tone="encouraging",
    )
