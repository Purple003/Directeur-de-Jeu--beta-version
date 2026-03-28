from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Course, Question
from ..services.file_service import extract_text
from ..services.llm_service import LLMConfigError, LLMServiceError, generate_mcq_questions
from ..services.question_service import _normalize_difficulty


class AdaptiveAIServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = int(status_code)


def generate_questions_for_course(
    db: Session,
    *,
    course_id: int,
    difficulty: str | None = None,
) -> int:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise AdaptiveAIServiceError("Course not found.", status_code=404)

    # Stateless pipeline: prefer `content_text` stored in DB (extracted from upload, no file storage).
    context_text = (getattr(course, "content_text", None) or course.description or "").strip()

    # Legacy fallback for old DB rows that stored a file_path.
    if not context_text and course.file_path:
        try:
            context_text = extract_text(course.file_path)
        except Exception:
            context_text = (course.description or "").strip()

    if not context_text:
        raise AdaptiveAIServiceError("Course has no content/description to generate from.", status_code=400)

    # Use difficulty as a hint via the "level" field (normalized later).
    level_hint = difficulty or course.level

    try:
        generated = generate_mcq_questions(
            subject=course.subject,
            level=level_hint,
            description=course.description,
            extracted_text=context_text,
        )
    except (LLMConfigError, LLMServiceError) as exc:
        raise AdaptiveAIServiceError(str(exc), status_code=502) from exc

    try:
        for item in generated:
            db.add(
                Question(
                    course_id=course.id,
                    question=item.question,
                    choices_json=item.choices,
                    correct_answer=item.correct_answer,
                    difficulty_level=_normalize_difficulty(item.difficulty_level),
                )
            )
        db.commit()
        return len(generated)
    except SQLAlchemyError as exc:
        db.rollback()
        raise AdaptiveAIServiceError("Failed to save generated questions.", status_code=500) from exc
