from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Course, Question
from ..schemas import LLMQuestion


class QuestionServiceError(Exception):
    """Raised when question persistence fails."""


_DIFFICULTY_MAP = {
    "beginner": "easy",
    "intermediate": "medium",
    "advanced": "hard",
}


def _normalize_difficulty(value: str) -> str:
    v = (value or "").strip().lower()
    if v in ("easy", "medium", "hard"):
        return v
    return _DIFFICULTY_MAP.get(v, value.strip() if value else "medium")


def create_course_and_questions(
    db: Session,
    *,
    professor_id: int | None = None,
    subject: str,
    level: str,
    description: str | None,
    file_path: str | None,
    content_text: str | None,
    questions: list[LLMQuestion],
) -> Course:
    try:
        course = Course(
            professor_id=professor_id,
            subject=subject.strip(),
            level=level.strip(),
            description=description.strip() if description else None,
            file_path=file_path,
            content_text=content_text.strip() if content_text else None,
        )
        db.add(course)
        db.flush()

        for item in questions:
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
        db.refresh(course)
        return course
    except SQLAlchemyError as exc:
        db.rollback()
        raise QuestionServiceError("Failed to save course/questions.") from exc


def get_questions_by_course_id(db: Session, course_id: int) -> list[Question]:
    return (
        db.query(Question)
        .filter(Question.course_id == course_id)
        .order_by(Question.id.asc())
        .all()
    )


def get_questions_by_course_id_and_difficulty(
    db: Session, course_id: int, difficulty: str
) -> list[Question]:
    diff = (difficulty or "").strip().lower()
    return (
        db.query(Question)
        .filter(Question.course_id == course_id)
        .filter(Question.difficulty_level.ilike(diff))
        .order_by(Question.id.asc())
        .all()
    )
