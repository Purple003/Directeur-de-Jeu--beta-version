from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ApiResponse, CourseQuestionsResponse, CourseQuestionsResponseItem
from ..services.question_service import get_questions_by_course_id, get_questions_by_course_id_and_difficulty
from ..utils.api_response import ok

router = APIRouter(tags=["Questions"])


@router.get("/courses/{course_id}/questions", response_model=ApiResponse[CourseQuestionsResponse])
def get_course_questions(course_id: int, db: Session = Depends(get_db)):
    # Backward-compatible endpoint
    questions = get_questions_by_course_id(db, course_id)
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for this course.")

    return ok(
        CourseQuestionsResponse(
            course_id=course_id,
            questions=[
                CourseQuestionsResponseItem(
                    id=item.id,
                    course_id=item.course_id,
                    question=item.question,
                    choices=item.choices_json,
                    correct_answer=item.correct_answer,
                    difficulty_level=item.difficulty_level,
                )
                for item in questions
            ],
        ).model_dump()
    )


@router.get("/questions/{course_id}", response_model=ApiResponse[CourseQuestionsResponse])
def get_questions(
    course_id: int,
    difficulty: str | None = Query(default=None, description="easy|medium|hard"),
    db: Session = Depends(get_db),
):
    if difficulty:
        questions = get_questions_by_course_id_and_difficulty(db, course_id, difficulty)
    else:
        questions = get_questions_by_course_id(db, course_id)

    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for this course.")

    return ok(
        CourseQuestionsResponse(
            course_id=course_id,
            questions=[
                CourseQuestionsResponseItem(
                    id=item.id,
                    course_id=item.course_id,
                    question=item.question,
                    choices=item.choices_json,
                    correct_answer=item.correct_answer,
                    difficulty_level=item.difficulty_level,
                )
                for item in questions
            ],
        ).model_dump()
    )
