from sqlalchemy.orm import Session

from ..models import Answer, GameSession, XAPIStatement


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


# ============================================================
# xAPI Statement Retrieval (Moodle/LRS Integration)
# ============================================================


def get_xapi_statements(
    db: Session,
    *,
    session_id: int | None = None,
    player_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[XAPIStatement], int]:
    """
    Query xAPI statements with optional filtering by session or player.

    Returns:
        (statements, total_count) where statements is a paginated list
        and total_count is the full count matching the filters (before pagination).

    Args:
        db: SQLAlchemy session
        session_id: Optional filter by session_id
        player_id: Optional filter by player_id (queries GameSession FK)
        limit: Number of results to return (1-1000, default 100)
        offset: Number of results to skip (default 0)

    This is a read-only query with no side effects.
    """
    # Start with base query
    q = db.query(XAPIStatement)

    # Filter by session_id if provided
    if session_id is not None and session_id > 0:
        q = q.filter(XAPIStatement.session_id == int(session_id))

    # Filter by player_id (requires join to GameSession)
    if player_id is not None and player_id > 0:
        q = q.join(GameSession, XAPIStatement.session_id == GameSession.id).filter(
            GameSession.player_id == int(player_id)
        )

    # Get total count before pagination
    total_count = q.count()

    # Apply pagination and ordering (newest first for LRS consumption)
    statements = (
        q.order_by(XAPIStatement.created_at.desc())
        .limit(int(limit))
        .offset(int(offset))
        .all()
    )

    return statements, total_count

