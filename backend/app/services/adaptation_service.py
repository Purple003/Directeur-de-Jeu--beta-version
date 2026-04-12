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


def apply_emotion_adjustment(difficulty: str, emotion_state: str | None) -> str:
    """
    Adjusts difficulty based on the 3-state Flow model.
    emotion_state: "stressed" | "bored" | "engaged"
    """
    if not emotion_state:
        return difficulty
    
    e = emotion_state.strip().lower()
    try:
        idx = _ORDER.index(difficulty)
    except ValueError:
        idx = 1  # default medium
    
    if e == "stressed":
        return _ORDER[max(0, idx - 1)]      # réduire difficulté
    if e == "bored":
        return _ORDER[min(2, idx + 1)]      # augmenter difficulté
    return difficulty                        # engaged = garder


def submit_score_and_recommend(db: Session, payload: SubmitScoreRequest) -> tuple[int, str]:
    base = compute_difficulty_from_score(payload.score)
    emotion_state = getattr(payload, 'emotion_state', None)
    recommended = apply_emotion_adjustment(base, emotion_state)

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
