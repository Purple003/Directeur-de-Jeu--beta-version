from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Course
from ..schemas import CourseCreate


class CourseServiceError(Exception):
    """Raised when course service operations fail."""


def create_course(db: Session, payload: CourseCreate) -> Course:
    try:
        course = Course(
            subject=payload.subject.strip(),
            level=payload.level.strip(),
            description=payload.description.strip() if payload.description else None,
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        return course
    except SQLAlchemyError as exc:
        db.rollback()
        raise CourseServiceError("Failed to create course") from exc
