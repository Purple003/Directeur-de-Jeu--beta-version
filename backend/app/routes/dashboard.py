from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Answer, Course, EmotionEvent, GameSession, Player
from ..services.auth_dependencies import require_role
from ..services.auth_service import AuthServiceError, authenticate, create_access_token
from ..config import env
from ..services.course_pipeline_service import CoursePipelineError, create_course_with_questions_from_upload
from ..services.analytics_service import get_course_results
from ..utils.api_response import ok

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ProfessorOnly = Depends(require_role("professor"))

def _get_owned_course(db: Session, *, course_id: int, professor_id: int) -> Course | None:
    return (
        db.query(Course)
        .filter(Course.id == course_id)
        .filter(Course.professor_id == professor_id)
        .first()
    )


@router.get("/login", response_class=HTMLResponse)
def dashboard_login(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def dashboard_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        user = authenticate(db, username=username, password=password)
        if user.role != "professor":
            raise AuthServiceError("Forbidden.")
        token = create_access_token(user=user)
    except AuthServiceError as exc:
        if "JWT_SECRET" in str(exc):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": str(exc)},
                status_code=500,
            )
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid credentials."}, status_code=401
        )

    resp = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    secure_cookie = (env("COOKIE_SECURE", "0") or "0").strip() == "1"
    resp.set_cookie("asg_token", token, httponly=True, samesite="lax", secure=secure_cookie)
    return resp


@router.post("/logout", status_code=status.HTTP_303_SEE_OTHER)
def dashboard_logout():
    resp = RedirectResponse(url="/dashboard/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("asg_token")
    return resp


@router.get("", response_class=HTMLResponse)
def dashboard_home(request: Request, db: Session = Depends(get_db), _user=ProfessorOnly):
    courses = (
        db.query(Course)
        .filter(Course.professor_id == _user.id)
        .order_by(Course.id.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"courses": courses},
    )


@router.get("/players", response_class=HTMLResponse)
def dashboard_players(request: Request, db: Session = Depends(get_db), _user=ProfessorOnly):
    # Compute per-player sessions + accuracy.
    rows = (
        db.query(
            Player,
            func.count(GameSession.id).label("total_sessions"),
            func.coalesce(func.avg(case((Answer.is_correct.is_(True), 1), else_=0)), 0).label("avg_correct"),
        )
        .outerjoin(GameSession, GameSession.player_id == Player.id)
        .outerjoin(Answer, Answer.session_id == GameSession.id)
        .group_by(Player.id)
        .order_by(Player.id.desc())
        .limit(200)
        .all()
    )

    players = []
    for p, total_sessions, avg_correct in rows:
        players.append(
            {
                "id": p.id,
                "name": p.name,
                "age": p.age,
                "school_level": p.school_level,
                "experience_level": p.experience_level,
                "game_level": int(getattr(p, "game_level", 1) or 1),
                "total_sessions": int(total_sessions or 0),
                "accuracy": float(avg_correct or 0.0),
            }
        )
    return templates.TemplateResponse(request, "players.html", {"players": players})


@router.get("/sessions", response_class=HTMLResponse)
def dashboard_sessions(request: Request, db: Session = Depends(get_db), _user=ProfessorOnly):
    # Recent sessions with computed accuracy.
    sessions = db.query(GameSession).order_by(GameSession.id.desc()).limit(200).all()
    items = []
    for s in sessions:
        total = db.query(func.count(Answer.id)).filter(Answer.session_id == s.id).scalar() or 0
        correct = (
            db.query(func.count(Answer.id))
            .filter(Answer.session_id == s.id)
            .filter(Answer.is_correct.is_(True))
            .scalar()
            or 0
        )
        accuracy = (correct / total) if total else 0.0
        duration_s = None
        if s.duration_ms is not None:
            duration_s = round(float(s.duration_ms) / 1000.0, 1)
        elif s.started_at and s.ended_at:
            duration_s = round((s.ended_at - s.started_at).total_seconds(), 1)

        player = db.query(Player).filter(Player.id == s.player_id).first()
        course = db.query(Course).filter(Course.id == s.course_id).first()
        items.append(
            {
                "id": s.id,
                "player_name": player.name if player else f"Player{s.player_id}",
                "course_subject": course.subject if course else f"Course{s.course_id}",
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "duration_s": duration_s if duration_s is not None else "-",
                "final_score": s.final_score,
                "accuracy": float(accuracy),
            }
        )
    return templates.TemplateResponse(request, "sessions.html", {"sessions": items})


@router.get("/analytics", response_class=HTMLResponse)
def dashboard_analytics(request: Request, db: Session = Depends(get_db), _user=ProfessorOnly):
    total_courses = db.query(func.count(Course.id)).scalar() or 0
    total_players = db.query(func.count(Player.id)).scalar() or 0
    total_sessions = db.query(func.count(GameSession.id)).scalar() or 0
    total_answers = db.query(func.count(Answer.id)).scalar() or 0
    correct_answers = db.query(func.count(Answer.id)).filter(Answer.is_correct.is_(True)).scalar() or 0
    accuracy = (correct_answers / total_answers) if total_answers else 0.0

    emo_rows = (
        db.query(EmotionEvent.emotion, func.count(EmotionEvent.id).label("c"))
        .group_by(EmotionEvent.emotion)
        .order_by(func.count(EmotionEvent.id).desc())
        .all()
    )
    emotions = [{"emotion": e, "count": int(c)} for e, c in emo_rows]

    summary = {
        "total_courses": int(total_courses),
        "total_players": int(total_players),
        "total_sessions": int(total_sessions),
        "total_answers": int(total_answers),
        "accuracy": float(accuracy),
    }
    return templates.TemplateResponse(
        request,
        "analytics.html",
        {"summary": summary, "emotions": emotions},
    )


@router.get("/course/{course_id}", response_class=HTMLResponse)
def dashboard_course(course_id: int, request: Request, db: Session = Depends(get_db), _user=ProfessorOnly):
    course = _get_owned_course(db, course_id=course_id, professor_id=int(_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return templates.TemplateResponse(
        request,
        "course.html",
        {"course": course},
    )


@router.get("/course/{course_id}/edit", response_class=HTMLResponse)
def dashboard_edit_course(
    course_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _user=ProfessorOnly,
):
    course = _get_owned_course(db, course_id=course_id, professor_id=int(_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    return templates.TemplateResponse(
        request,
        "edit_course.html",
        {"course": course},
    )


@router.post("/course/{course_id}/update", status_code=status.HTTP_303_SEE_OTHER)
def dashboard_update_course(
    course_id: int,
    subject: str = Form(...),
    level: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    _user=ProfessorOnly,
):
    course = _get_owned_course(db, course_id=course_id, professor_id=int(_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    try:
        course.subject = subject.strip()
        course.level = level.strip()
        course.description = description.strip() if description.strip() else None
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to update course right now.") from exc

    return RedirectResponse(
        url=f"/dashboard/course/{course.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/course/{course_id}/delete", status_code=status.HTTP_303_SEE_OTHER)
def dashboard_delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    _user=ProfessorOnly,
):
    course = _get_owned_course(db, course_id=course_id, professor_id=int(_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    try:
        db.delete(course)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to delete course right now.") from exc

    return RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/create-course", status_code=status.HTTP_303_SEE_OTHER)
def dashboard_create_course(
    subject: str = Form(...),
    level: str = Form(...),
    description: str = Form(""),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    _user=ProfessorOnly,
):
    try:
        course = create_course_with_questions_from_upload(
            db,
            professor_id=int(_user.id),
            subject=subject,
            level=level,
            description=description,
            file=file,
        )
    except CoursePipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(url=f"/dashboard/course/{course.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/api/course/{course_id}/results")
def dashboard_course_results(course_id: int, db: Session = Depends(get_db), _user=ProfessorOnly):
    course = _get_owned_course(db, course_id=course_id, professor_id=int(_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return ok(get_course_results(db, course_id))


@router.get("/api/course/{course_id}/emotion-summary")
def dashboard_emotion_summary(
    course_id: int,
    session_id: int | None = Query(default=None, ge=1, description="Optional: include latest emotion for this session"),
    db: Session = Depends(get_db),
    _user=ProfessorOnly,
):
    course = _get_owned_course(db, course_id=course_id, professor_id=int(_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    # Aggregate emotion counts for the course via sessions.
    sessions = db.query(GameSession.id).filter(GameSession.course_id == course_id).subquery()
    rows = (
        db.query(EmotionEvent.emotion, func.count(EmotionEvent.id))
        .filter(EmotionEvent.session_id.in_(sessions))
        .group_by(EmotionEvent.emotion)
        .all()
    )

    payload: dict = {"course_id": course_id, "counts": {emotion: int(count) for emotion, count in rows}}

    latest = (
        db.query(EmotionEvent)
        .filter(EmotionEvent.session_id.in_(sessions))
        .order_by(EmotionEvent.created_at.desc(), EmotionEvent.id.desc())
        .first()
    )
    if latest:
        payload["latest"] = {
            "session_id": int(latest.session_id),
            "emotion": str(latest.emotion),
            "confidence": float(latest.confidence),
            "created_at": latest.created_at.isoformat() if latest.created_at else None,
        }

    if session_id is not None:
        s = db.query(GameSession).filter(GameSession.id == int(session_id)).first()
        if s and int(s.course_id) == int(course_id):
            ev = (
                db.query(EmotionEvent)
                .filter(EmotionEvent.session_id == int(session_id))
                .order_by(EmotionEvent.created_at.desc(), EmotionEvent.id.desc())
                .first()
            )
            if ev:
                payload["latest_for_session"] = {
                    "session_id": int(ev.session_id),
                    "emotion": str(ev.emotion),
                    "confidence": float(ev.confidence),
                    "created_at": ev.created_at.isoformat() if ev.created_at else None,
                }
            else:
                payload["latest_for_session"] = None
        else:
            payload["latest_for_session"] = None

    return ok(payload)


@router.get("/api/course/{course_id}/question-stats")
def dashboard_question_stats(course_id: int, db: Session = Depends(get_db), _user=ProfessorOnly):
    course = _get_owned_course(db, course_id=course_id, professor_id=int(_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    # Accuracy per question for this course.
    rows = (
        db.query(
            Answer.question_id,
            func.count(Answer.id).label("total"),
            func.sum(case((Answer.is_correct.is_(True), 1), else_=0)).label("correct"),
            func.avg(Answer.time_spent_ms).label("avg_time_ms"),
        )
        .join(GameSession, Answer.session_id == GameSession.id)
        .filter(GameSession.course_id == course_id)
        .group_by(Answer.question_id)
        .order_by(func.count(Answer.id).desc())
        .all()
    )

    return ok(
        {
            "course_id": course_id,
            "questions": [
                {
                    "question_id": int(qid),
                    "total_answers": int(total or 0),
                    "correct_answers": int(correct or 0),
                    "accuracy": float((correct or 0) / (total or 1)) if total else 0.0,
                    "avg_time_ms": int(avg_time_ms) if avg_time_ms is not None else None,
                }
                for (qid, total, correct, avg_time_ms) in rows
            ],
        }
    )


@router.get("/api/course/{course_id}/response-time")
def dashboard_response_time(course_id: int, db: Session = Depends(get_db), _user=ProfessorOnly):
    course = _get_owned_course(db, course_id=course_id, professor_id=int(_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    # Overall average response time for this course.
    avg_ms = (
        db.query(func.avg(Answer.time_spent_ms))
        .join(GameSession, Answer.session_id == GameSession.id)
        .filter(GameSession.course_id == course_id)
        .scalar()
    )
    return ok({"course_id": course_id, "avg_time_ms": int(avg_ms) if avg_ms is not None else None})
