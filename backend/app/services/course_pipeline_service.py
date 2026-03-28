from fastapi import UploadFile
from sqlalchemy.orm import Session

from .file_service import FileServiceError, extract_text_from_upload
from .llm_service import LLMConfigError, LLMServiceError, generate_mcq_questions
from .question_service import QuestionServiceError, create_course_and_questions
from ..langchain_pipeline.pipeline import build_retrieval_context


class CoursePipelineError(Exception):
    pass


def create_course_with_questions_from_upload(
    db: Session,
    *,
    professor_id: int | None = None,
    subject: str,
    level: str,
    description: str,
    file: UploadFile | None,
):
    try:
        extracted_text = ""
        if file is not None:
            # Stateless: extract text from the upload without storing it on disk.
            raw_text = extract_text_from_upload(file)
            if not raw_text:
                raise CoursePipelineError("Uploaded file has no extractable text.")

            # Prefer retrieval context (keeps prompt size bounded).
            query = f"{subject}. {description}".strip()
            lc = build_retrieval_context(raw_text=raw_text, query=query)
            extracted_text = (lc.context_text or "").strip() or raw_text.strip()

        # Allow creating a course without a file: use description as context.
        if not extracted_text and not (description or "").strip():
            raise CoursePipelineError("Provide either a file or a non-empty description.")

        generated_questions = generate_mcq_questions(
            subject=subject,
            level=level,
            description=description,
            extracted_text=extracted_text or description,
        )

        course = create_course_and_questions(
            db,
            professor_id=professor_id,
            subject=subject,
            level=level,
            description=description,
            file_path=None,
            content_text=extracted_text or description,
            questions=generated_questions,
        )
        return course
    except FileServiceError as exc:
        raise CoursePipelineError(str(exc)) from exc
    except (LLMConfigError, LLMServiceError, QuestionServiceError) as exc:
        raise CoursePipelineError(str(exc)) from exc
