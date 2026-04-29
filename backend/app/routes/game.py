import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    ApiResponse,
    EndSessionRequest,
    EndSessionResponse,
    GenerateDialogueRequest,
    GenerateDialogueResponse,
    GameQuestionsResponse,
    GameQuestionItem,
    ProgressionState,
    StartSessionRequest,
    StartSessionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    UpdateProgressRequest,
    UpdateProgressResponse,
    NextQuestionResponse,
)
from ..services.game_service import GameServiceError, end_session, start_session, submit_answer
from ..services.progression_service import recommend_difficulty
from ..services.adaptive_question_service import (
    AdaptiveQuestionServiceError,
    decide_next_question,
    list_next_questions,
)
from ..models import Course, GameSession, Player, LevelProgress, Question
from ..services.llm_service import LLMConfigError, LLMServiceError, generate_wizard_dialogue
from ..utils.api_response import ok

router = APIRouter(prefix="/game", tags=["Game"])
logger = logging.getLogger(__name__)


@router.post(
    "/generate-dialogue",
    response_model=ApiResponse[GenerateDialogueResponse],
    status_code=status.HTTP_200_OK,
)
def generate_dialogue(payload: GenerateDialogueRequest, db: Session = Depends(get_db)):
    """
    Generates a short, course-specific explanation for the wizard NPC.

    This endpoint is designed for Unity dialogue UI:
    - `repeat` can call again for a fresh phrasing.
    - `simplify` sets payload.simplify=true for simpler output.
    """
    course = db.query(Course).filter(Course.id == int(payload.course_id)).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    session = db.query(GameSession).filter(GameSession.id == int(payload.session_id)).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if int(session.course_id) != int(payload.course_id):
        raise HTTPException(status_code=400, detail="session_id does not belong to this course.")

    context_text = (getattr(course, "content_text", None) or course.description or "").strip()
    if not context_text:
        context_text = f"{(course.subject or '').strip()}\n{(course.description or '').strip()}".strip()

    try:
        text = generate_wizard_dialogue(
            subject=(course.subject or "").strip(),
            level=(course.level or "").strip(),
            description=(course.description or "").strip(),
            extracted_text=context_text,
            simplify=bool(payload.simplify),
        )
    except (LLMConfigError, LLMServiceError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception:
        logger.exception("[API] GenerateDialogue unhandled error session_id=%s course_id=%s", payload.session_id, payload.course_id)
        raise HTTPException(status_code=500, detail="Unable to generate dialogue right now.")

    return ok(
        GenerateDialogueResponse(
            session_id=int(payload.session_id),
            course_id=int(payload.course_id),
            simplified=bool(payload.simplify),
            dialogue_text=(text or "").strip(),
        ).model_dump()
    )


@router.get("/questions/{course_id}", response_model=ApiResponse[GameQuestionsResponse])
def get_game_questions(
    course_id: int,
    session_id: int | None = Query(default=None, ge=1, description="Optional: session id to exclude answered questions"),
    player_id: int | None = Query(default=None, description="Optional: use player progression to pick difficulty"),
    difficulty: str | None = Query(default=None, description="easy|medium|hard"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Deterministic question list for Unity:
    - No randomness.
    - If `session_id` is provided: excludes already-answered questions and uses adaptive difficulty.
    - Else: falls back to difficulty/player_id filters for tooling/debug.
    """
    logger.info(
        "[API] GetQuestions course_id=%s session_id=%s player_id=%s difficulty=%s limit=%s",
        course_id,
        session_id,
        player_id,
        difficulty,
        limit,
    )

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    recommended: str | None = None
    questions: list[Question] = []

    if session_id is not None:
        try:
            recommended, questions = list_next_questions(db, session_id=int(session_id), limit=int(limit))
        except AdaptiveQuestionServiceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # Safety: ensure the session course matches this course_id (even when no questions remain).
        s = db.query(GameSession).filter(GameSession.id == int(session_id)).first()
        if s and int(s.course_id) != int(course_id):
            raise HTTPException(status_code=400, detail="session_id does not belong to this course.")
    else:
        # Debugging path (not used by the adaptive Unity flow).
        if not difficulty and player_id is not None:
            player = db.query(Player).filter(Player.id == int(player_id)).first()
            if player:
                level = int(getattr(player, "game_level", 1) or 1)
                recommended = recommend_difficulty(level_number=level, accuracy=0.0, avg_time_ms=None, emotion=None)
                difficulty = recommended

        q = db.query(Question).filter(Question.course_id == course_id)
        if difficulty:
            q = q.filter(Question.difficulty_level.ilike(str(difficulty).strip().lower()))
        questions = q.order_by(Question.id.asc()).limit(int(limit)).all()

    return ok(
        GameQuestionsResponse(
            course_id=course_id,
            recommended_difficulty=recommended,
            questions=[
                GameQuestionItem(
                    id=q.id,
                    course_id=q.course_id,
                    question=q.question,
                    choices=q.choices_json,
                    correct_answer=q.correct_answer,
                    difficulty_level=q.difficulty_level,
                )
                for q in (questions or [])
            ],
        ).model_dump()
    )


@router.get(
    "/sessions/{session_id}/next-question",
    response_model=ApiResponse[NextQuestionResponse],
    status_code=status.HTTP_200_OK,
)
def get_next_question(session_id: int, db: Session = Depends(get_db)):
    """
    Server-controlled adaptive question selection.
    Unity must call this endpoint for every quiz trigger (no random selection client-side).
    """
    try:
        decision = decide_next_question(db, session_id=int(session_id))
    except AdaptiveQuestionServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    q = decision.question
    q_item = None
    if q is not None:
        q_item = GameQuestionItem(
            id=q.id,
            course_id=q.course_id,
            question=decision.adapted_question_text or q.question,
            choices=q.choices_json,
            correct_answer=q.correct_answer,
            difficulty_level=q.difficulty_level,
            hint=decision.hint,
            tone=decision.tone,
        )

    return ok(
        NextQuestionResponse(
            session_id=decision.session_id,
            course_id=decision.course_id,
            player_level=decision.player_level,
            recommended_difficulty=decision.recommended_difficulty,
            question=q_item,
            remaining_in_difficulty=decision.remaining_in_recommended,
            remaining_total=decision.remaining_total,
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

    # Best-effort: include initial recommended difficulty + first question so Unity can follow server decisions.
    recommended: str | None = None
    next_q: GameQuestionItem | None = None
    try:
        decision = decide_next_question(db, session_id=int(session.id))
        recommended = decision.recommended_difficulty
        if decision.question is not None:
            q = decision.question
            next_q = GameQuestionItem(
                id=q.id,
                course_id=q.course_id,
                question=q.question,
                choices=q.choices_json,
                correct_answer=q.correct_answer,
                difficulty_level=q.difficulty_level,
            )
    except Exception:
        recommended, next_q = None, None

    return ok(
        StartSessionResponse(
            message="Session started",
            session_id=session.id,
            recommended_difficulty=recommended,
            next_question=next_q,
        ).model_dump()
    )


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
