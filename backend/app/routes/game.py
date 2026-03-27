import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    ApiResponse,
    EndSessionRequest,
    EndSessionResponse,
    GameQuestionsResponse,
    GameQuestionItem,
    ProgressionState,
    StartSessionRequest,
    StartSessionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    UpdateProgressRequest,
    UpdateProgressResponse,
)
from ..services.game_service import GameServiceError, end_session, start_session, submit_answer
from ..services.progression_service import recommend_difficulty
from ..models import Course, Player, LevelProgress, Question
from ..utils.api_response import ok

router = APIRouter(prefix="/game", tags=["Game"])
logger = logging.getLogger(__name__)


@router.get("/questions/{course_id}", response_model=ApiResponse[GameQuestionsResponse])
def get_game_questions(
    course_id: int,
    player_id: int | None = Query(default=None, description="Optional: use player progression to pick difficulty"),
    difficulty: str | None = Query(default=None, description="easy|medium|hard"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # TEMPORARY: disable all adaptive filtering to make Unity stable.
    # - No progression-based difficulty selection.
    # - No difficulty filter.
    # - No "already answered" filter.
    # - No limit slice (return ALL questions for the course).
    #
    # Only return 404 if the course_id does not exist.
    logger.info(
        "[API] GetQuestions course_id=%s player_id=%s difficulty=%s limit=%s (filters disabled)",
        course_id,
        player_id,
        difficulty,
        limit,
    )

    try:
        course = db.query(Course).filter(Course.id == course_id).first()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found.")

        questions = (
            db.query(Question)
            .filter(Question.course_id == course_id)
            .order_by(Question.id.asc())
            .all()
        )
        logger.info("[API] GetQuestions found=%s (before filtering) course_id=%s", len(questions or []), course_id)
    except HTTPException:
        raise
    except Exception:
        # Unity stability requirement: never crash this endpoint.
        logger.exception("[API] GetQuestions ERROR course_id=%s (returning empty list)", course_id)
        try:
            db.rollback()
        except Exception:
            pass
        questions = []

    if not questions:
        logger.warning("[API] No questions found for course %s", course_id)
        questions = []

    return ok(
        GameQuestionsResponse(
            course_id=course_id,
            questions=[
                GameQuestionItem(
                    id=q.id,
                    course_id=q.course_id,
                    question=q.question,
                    choices=q.choices_json,
                    correct_answer=q.correct_answer,
                    difficulty_level=q.difficulty_level,
                )
                for q in questions
            ],
        ).model_dump()
    )


@router.get("/progression/{player_id}/{course_id}", response_model=ApiResponse[ProgressionState])
def get_progression_state(player_id: int, course_id: int, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")

    last = (
        db.query(LevelProgress)
        .filter(LevelProgress.player_id == player_id)
        .filter(LevelProgress.course_id == course_id)
        .order_by(LevelProgress.id.desc())
        .first()
    )
    level = int(getattr(player, "game_level", 1) or 1)
    if last and last.recommended_difficulty:
        diff = last.recommended_difficulty
        level = int(last.level_number or level)
    else:
        diff = recommend_difficulty(level_number=level, accuracy=0.0, avg_time_ms=None, emotion=None)

    return ok(ProgressionState(player_id=player_id, course_id=course_id, level=level, recommended_difficulty=diff).model_dump())


@router.post("/update-progress", response_model=ApiResponse[UpdateProgressResponse], status_code=status.HTTP_200_OK)
def update_progress(payload: UpdateProgressRequest, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == payload.player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")

    try:
        player.xp = max(0, int(getattr(player, "xp", 0) or 0) + int(payload.xp_delta or 0))
        player.stars = max(0, int(getattr(player, "stars", 0) or 0) + int(payload.stars_delta or 0))
        db.commit()
        db.refresh(player)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to update progress right now.")

    return ok(
        UpdateProgressResponse(
            message="Progress updated",
            player_id=player.id,
            xp=int(player.xp or 0),
            stars=int(player.stars or 0),
            game_level=int(getattr(player, "game_level", 1) or 1),
        ).model_dump()
    )


@router.post(
    "/start-session",
    response_model=ApiResponse[StartSessionResponse],
    status_code=status.HTTP_201_CREATED,
)
def start_game_session(payload: StartSessionRequest, db: Session = Depends(get_db)):
    logger.info("[API] StartSession payload=%s", payload.model_dump())
    try:
        session = start_session(db, player_id=payload.player_id, course_id=payload.course_id)
    except GameServiceError as exc:
        logger.warning("[API] StartSession ERROR player_id=%s course_id=%s msg=%s", payload.player_id, payload.course_id, str(exc))
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    return ok(StartSessionResponse(message="Session started", session_id=session.id).model_dump())


@router.post(
    "/submit-answer",
    response_model=ApiResponse[SubmitAnswerResponse],
    status_code=status.HTTP_201_CREATED,
)
def submit_game_answer(payload: SubmitAnswerRequest, db: Session = Depends(get_db)):
    # Swagger/OpenAPI: using a Pydantic model here ensures `/docs` shows all fields properly.
    # Validation errors are handled by FastAPI (422) instead of turning into 500s.
    logger.info("[API] SubmitAnswer payload=%s", payload.model_dump())
    try:
        is_correct = submit_answer(
            db,
            session_id=payload.session_id,
            question_id=payload.question_id,
            selected_answer=payload.selected_answer,
            time_spent_ms=payload.time_spent_ms,
            emotion=payload.emotion,
            confidence=payload.confidence,
        )
    except GameServiceError as exc:
        logger.warning("[API] SubmitAnswer ERROR session_id=%s question_id=%s msg=%s", payload.session_id, payload.question_id, str(exc))
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception:
        logger.exception("[API] SubmitAnswer ERROR session_id=%s question_id=%s unhandled", payload.session_id, payload.question_id)
        raise HTTPException(status_code=500, detail="Unable to submit answer right now.")

    logger.info("[API] SubmitAnswer OK session_id=%s question_id=%s correct=%s", payload.session_id, payload.question_id, bool(is_correct))
    return ok(SubmitAnswerResponse(message="Answer saved", is_correct=bool(is_correct)).model_dump())


@router.post(
    "/end-session",
    response_model=ApiResponse[EndSessionResponse],
    status_code=status.HTTP_200_OK,
)
def end_game_session(payload: EndSessionRequest, db: Session = Depends(get_db)):
    logger.info("[API] EndSession payload=%s", payload.model_dump())
    try:
        session, duration_ms, next_level, recommended = end_session(
            db, session_id=payload.session_id, final_score=payload.final_score
        )
    except GameServiceError as exc:
        logger.warning("[API] EndSession ERROR session_id=%s msg=%s", payload.session_id, str(exc))
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception:
        logger.exception("[API] EndSession ERROR session_id=%s unhandled", payload.session_id)
        raise HTTPException(status_code=500, detail="Unable to end session right now.")

    logger.info("[API] EndSession OK session_id=%s final_score=%s duration_ms=%s", payload.session_id, float(session.final_score or 0.0), duration_ms)
    return ok(
        EndSessionResponse(
            message="Session ended",
            session_id=session.id,
            final_score=float(session.final_score or 0.0),
            duration_ms=duration_ms,
            next_level=next_level,
            recommended_difficulty=recommended,
        ).model_dump()
    )
