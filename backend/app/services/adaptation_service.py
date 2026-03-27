from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import PlayerProgress
from ..schemas import SubmitScoreRequest


class AdaptationServiceError(Exception):
    pass


_ORDER = ["easy", "medium", "hard"]


def compute_difficulty_from_score(score: float) -> str:
    if score < 50:
        return "easy"
    if score <= 80:
        return "medium"
    return "hard"


def apply_emotion_adjustment(difficulty: str, emotion_score: float | None) -> str:
    """
    emotion_score is reserved for future emotion pipelines.
    For now we treat high values as frustration and reduce difficulty by one level.
    """
    if emotion_score is None:
        return difficulty

    frustration_threshold = 70.0
    if emotion_score < frustration_threshold:
        return difficulty

    try:
        idx = _ORDER.index(difficulty)
    except ValueError:
        return difficulty

    return _ORDER[max(0, idx - 1)]


def submit_score_and_recommend(db: Session, payload: SubmitScoreRequest) -> tuple[int, str]:
    base = compute_difficulty_from_score(payload.score)
    recommended = apply_emotion_adjustment(base, payload.emotion_score)

    try:
        row = PlayerProgress(
            player_id=payload.player_id,
            course_id=payload.course_id,
            score=float(payload.score),
            emotion_score=float(payload.emotion_score) if payload.emotion_score is not None else None,
            difficulty_level=recommended,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id), recommended
    except SQLAlchemyError as exc:
        db.rollback()
        raise AdaptationServiceError("Failed to save player progress.") from exc
