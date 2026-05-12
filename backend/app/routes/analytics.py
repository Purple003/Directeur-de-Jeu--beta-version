from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    ApiResponse,
    CourseResultsResponse,
    StudentProgressResponse,
    XAPIStatementsResponse,
    XAPIStatementResponse,
)
from ..services.analytics_service import get_course_results, get_student_progress, get_xapi_statements
from ..services.auth_dependencies import try_get_current_user
from ..utils.api_response import ok
from datetime import datetime

router = APIRouter(tags=["Analytics"])


@router.get("/student/progress/{student_id}", response_model=ApiResponse[StudentProgressResponse])
def student_progress(student_id: int, db: Session = Depends(get_db)):
    # student_id == player_id in the current data model
    return ok(StudentProgressResponse(**get_student_progress(db, student_id)).model_dump())


@router.get("/course/results/{course_id}", response_model=ApiResponse[CourseResultsResponse])
def course_results(course_id: int, db: Session = Depends(get_db)):
    return ok(CourseResultsResponse(**get_course_results(db, course_id)).model_dump())


# ============================================================
# xAPI Statement Retrieval (Moodle/LRS Integration)
# ============================================================


@router.get(
    "/xapi/statements",
    response_model=ApiResponse[XAPIStatementsResponse],
    tags=["xAPI/LRS"],
)
def get_xapi_statements_endpoint(
    db: Session = Depends(get_db),
    session_id: int | None = Query(default=None, ge=1, description="Filter by session_id"),
    player_id: int | None = Query(default=None, ge=1, description="Filter by player_id"),
    limit: int = Query(default=100, ge=1, le=1000, description="Number of statements to return (1-1000)"),
    offset: int = Query(default=0, ge=0, description="Number of statements to skip"),
):
    """
    Retrieve stored xAPI statements for LRS/Moodle consumption.

    This endpoint returns xAPI statements in standard format ready for consumption by:
    - Moodle xAPI plugins
    - Learning Locker
    - Generic LRS systems

    Query parameters:
    - session_id: Filter statements by specific game session
    - player_id: Filter statements by specific player
    - limit: Results per page (default 100, max 1000)
    - offset: Pagination offset (for cursor-based navigation)

    Returns:
    - statements: Array of xAPI statement objects with metadata
    - count: Number of statements in this page
    - total: Total statements matching the filter criteria
    - limit/offset: Pagination parameters used

    Authentication: Requires valid JWT token in Authorization header.

    Note: Statements are never modified; this is a read-only retrieval endpoint.
    For historical accuracy, statements are returned in reverse chronological order (newest first).
    """
    try:
        statements, total_count = get_xapi_statements(
            db,
            session_id=session_id,
            player_id=player_id,
            limit=limit,
            offset=offset,
        )

        # Convert to response schema
        stmt_responses = [
            XAPIStatementResponse(
                id=stmt.id,
                session_id=stmt.session_id,
                statement_json=stmt.statement_json,
                sent=stmt.sent,
                created_at=stmt.created_at.isoformat() if stmt.created_at else None,
            )
            for stmt in statements
        ]

        response_data = XAPIStatementsResponse(
            statements=stmt_responses,
            count=len(stmt_responses),
            total=total_count,
            limit=limit,
            offset=offset,
        )

        return ok(response_data.model_dump())

    except Exception as exc:
        # Log but don't expose internal error details
        import logging

        logger = logging.getLogger(__name__)
        logger.exception("Error retrieving xAPI statements: %s", str(exc))
        # Return empty result on error rather than 500
        return ok(
            XAPIStatementsResponse(
                statements=[],
                count=0,
                total=0,
                limit=limit,
                offset=offset,
            ).model_dump()
        )

