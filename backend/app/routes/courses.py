from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course

router = APIRouter(tags=["Courses"])


class CourseListItem(BaseModel):
    id: int
    name: str


@router.get("/courses", response_model=list[CourseListItem], status_code=status.HTTP_200_OK)
def list_courses(db: Session = Depends(get_db)) -> list[CourseListItem]:
    courses = db.query(Course).order_by(Course.id.asc()).all()
    return [CourseListItem(id=int(course.id), name=course.subject) for course in courses]
