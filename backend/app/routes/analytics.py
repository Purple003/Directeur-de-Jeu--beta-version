from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ApiResponse, CourseResultsResponse, StudentProgressResponse
from ..services.analytics_service import get_course_results, get_student_progress
from ..utils.api_response import ok

router = APIRouter(tags=["Analytics"])


@router.get("/student/progress/{student_id}", response_model=ApiResponse[StudentProgressResponse])
def student_progress(student_id: int, db: Session = Depends(get_db)):
    # student_id == player_id in the current data model
    return ok(StudentProgressResponse(**get_student_progress(db, student_id)).model_dump())


@router.get("/course/results/{course_id}", response_model=ApiResponse[CourseResultsResponse])
def course_results(course_id: int, db: Session = Depends(get_db)):
    return ok(CourseResultsResponse(**get_course_results(db, course_id)).model_dump())
