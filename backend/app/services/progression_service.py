from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Answer, EmotionEvent, LevelProgress, Player


class ProgressionServiceError(Exception):
    pass


_ORDER = ["easy", "medium", "hard"]


def compute_session_metrics(db: Session, *, session_id: int) -> tuple[float, int | None, str | None]:
    answers = db.query(Answer).filter(Answer.session_id == session_id).all()
    if not answers:
        return 0.0, None, None

    correct = sum(1 for a in answers if a.is_correct)
    accuracy = correct / len(answers)

    times = [a.time_spent_ms for a in answers if a.time_spent_ms is not None]
    avg_time_ms = int(sum(times) / len(times)) if times else None

    # Most recent emotion event (if any) during the session.
    emo = (
        db.query(EmotionEvent)
        .filter(EmotionEvent.session_id == session_id)
        .order_by(EmotionEvent.id.desc())
        .first()
    )
    emotion = emo.emotion if emo else None
    return float(accuracy), avg_time_ms, emotion


def recommend_difficulty(
    *, level_number: int, accuracy: float, avg_time_ms: int | None, emotion: str | None
) -> str:
    # Base difficulty by level for levels 1-4.
    if level_number <= 1:
        diff = "easy"
    elif level_number == 2:
        diff = "medium"
    else:
        diff = "hard"

    # Level 5 is adaptive: start from accuracy.
    if level_number >= 5:
        if accuracy < 0.5:
            diff = "easy"
        elif accuracy <= 0.8:
            diff = "medium"
        else:
            diff = "hard"

    diff = _shift_by_accuracy(diff, accuracy)
    diff = _shift_by_time(diff, avg_time_ms)
    diff = _shift_by_emotion(diff, emotion)
    return diff


def advance_level(*, current_level: int, accuracy: float) -> int:
    # Boss level (4) is stricter.
    pass_threshold = 0.8 if current_level == 4 else 0.7
    if accuracy >= pass_threshold:
        return min(5, current_level + 1)
    if accuracy < 0.5:
        return max(1, current_level - 1)
    return current_level


def update_progression_for_session(
    db: Session,
    *,
    player_id: int,
    course_id: int,
    session_id: int,
) -> tuple[int, int, str, bool]:
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise ProgressionServiceError("Player not found.")

    accuracy, avg_time_ms, emotion = compute_session_metrics(db, session_id=session_id)
    current_level = int(player.game_level or 1)
    next_level = advance_level(current_level=current_level, accuracy=accuracy)
    passed = next_level > current_level
    recommended = recommend_difficulty(
        level_number=next_level,
        accuracy=accuracy,
        avg_time_ms=avg_time_ms,
        emotion=emotion,
    )

    # Persist player state + snapshot row.
    player.game_level = next_level
    db.add(
        LevelProgress(
            player_id=player_id,
            course_id=course_id,
            session_id=session_id,
            level_number=next_level,
            accuracy=float(accuracy),
            avg_time_ms=avg_time_ms,
            emotion=emotion,
            recommended_difficulty=recommended,
        )
    )

    return current_level, next_level, recommended, passed


def _shift(diff: str, delta: int) -> str:
    try:
        i = _ORDER.index(diff)
    except ValueError:
        i = 1
    return _ORDER[max(0, min(len(_ORDER) - 1, i + delta))]


def _shift_by_accuracy(diff: str, accuracy: float) -> str:
    if accuracy > 0.85:
        return _shift(diff, +1)
    if accuracy < 0.5:
        return _shift(diff, -1)
    return diff


def _shift_by_time(diff: str, avg_time_ms: int | None) -> str:
    if avg_time_ms is None:
        return diff
    if avg_time_ms < 3000:
        return _shift(diff, +1)
    if avg_time_ms > 8000:
        return _shift(diff, -1)
    return diff


def _shift_by_emotion(diff: str, emotion: str | None) -> str:
    e = (emotion or "").strip().lower()
    if e in ("frustrated", "stress", "confused"):
        return _shift(diff, -1)
    if e in ("focused", "happy"):
        return _shift(diff, +1)
    return diff
