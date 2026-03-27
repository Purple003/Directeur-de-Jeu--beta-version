from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ApiResponse, CourseCreateResponse, GenerateQuestionsRequest, GenerateQuestionsResponse
from ..services.auth_dependencies import require_role
from ..models import Course
from ..services.adaptive_ai_service import AdaptiveAIServiceError, generate_questions_for_course
from ..services.course_pipeline_service import (
    CoursePipelineError,
    create_course_with_questions_from_upload,
)
from ..utils.api_response import ok

router = APIRouter(prefix="/professor", tags=["Professor"])

ProfessorOnly = Depends(require_role("professor"))


@router.post(
    "/create-course",
    response_model=ApiResponse[CourseCreateResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_course_endpoint(
    subject: str = Form(..., min_length=1, max_length=255),
    level: str = Form(..., min_length=1, max_length=255),
    description: str = Form("", max_length=5000),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user=ProfessorOnly,
):
    try:
        course = create_course_with_questions_from_upload(
            db,
            professor_id=int(user.id),
            subject=subject,
            level=level,
            description=description,
            file=file,
        )

        return ok(
            CourseCreateResponse(
                message="Course and questions generated successfully",
                course_id=course.id,
            ).model_dump()
        )
    except CoursePipelineError as exc:
        # Intentionally keep message safe/clean for Unity.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/courses/{course_id}/generate-questions",
    response_model=ApiResponse[GenerateQuestionsResponse],
    status_code=status.HTTP_201_CREATED,
)
def generate_more_questions(
    course_id: int,
    payload: GenerateQuestionsRequest,
    db: Session = Depends(get_db),
    user=ProfessorOnly,
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course or course.professor_id != user.id:
        raise HTTPException(status_code=404, detail="Course not found.")

    try:
        created = generate_questions_for_course(db, course_id=course_id, difficulty=payload.difficulty)
    except AdaptiveAIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ok(
        GenerateQuestionsResponse(
            message="Questions generated successfully",
            course_id=course_id,
            created=int(created),
        ).model_dump()
    )
