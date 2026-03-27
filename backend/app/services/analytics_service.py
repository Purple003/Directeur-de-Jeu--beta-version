from sqlalchemy.orm import Session

from ..models import Answer, GameSession


def get_student_progress(db: Session, player_id: int) -> dict:
    sessions = db.query(GameSession).filter(GameSession.player_id == player_id).count()
    total_answers = (
        db.query(Answer)
        .join(GameSession, Answer.session_id == GameSession.id)
        .filter(GameSession.player_id == player_id)
        .count()
    )
    correct_answers = (
        db.query(Answer)
        .join(GameSession, Answer.session_id == GameSession.id)
        .filter(GameSession.player_id == player_id)
        .filter(Answer.is_correct.is_(True))
        .count()
    )
    accuracy = (correct_answers / total_answers) if total_answers else 0.0
    return {
        "player_id": player_id,
        "total_sessions": sessions,
        "total_answers": total_answers,
        "correct_answers": correct_answers,
        "accuracy": round(accuracy, 4),
    }


def get_course_results(db: Session, course_id: int) -> dict:
    sessions = db.query(GameSession).filter(GameSession.course_id == course_id).count()
    total_answers = (
        db.query(Answer)
        .join(GameSession, Answer.session_id == GameSession.id)
        .filter(GameSession.course_id == course_id)
        .count()
    )
    correct_answers = (
        db.query(Answer)
        .join(GameSession, Answer.session_id == GameSession.id)
        .filter(GameSession.course_id == course_id)
        .filter(Answer.is_correct.is_(True))
        .count()
    )
    accuracy = (correct_answers / total_answers) if total_answers else 0.0
    return {
        "course_id": course_id,
        "total_sessions": sessions,
        "total_answers": total_answers,
        "correct_answers": correct_answers,
        "accuracy": round(accuracy, 4),
    }

