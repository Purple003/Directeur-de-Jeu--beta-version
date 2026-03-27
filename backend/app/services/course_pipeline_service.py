from fastapi import UploadFile
from sqlalchemy.orm import Session

from pathlib import Path

from .file_service import FileServiceError, delete_file_if_exists, extract_text, save_uploaded_file
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
    saved_file_path: str | None = None
    try:
        extracted_text = ""
        if file is not None:
            saved_file_path = save_uploaded_file(file)
            # Prefer LangChain retrieval context if available; fall back to direct extraction.
            try:
                base_dir = Path(__file__).resolve().parents[2]
                abs_path = str((base_dir / saved_file_path).resolve())
                query = f"{subject}. {description}".strip()
                lc = build_retrieval_context(file_path=abs_path, query=query)
                extracted_text = (lc.context_text or "").strip()
            except Exception:
                extracted_text = ""

            if not extracted_text:
                extracted_text = extract_text(saved_file_path)
            if not extracted_text:
                delete_file_if_exists(saved_file_path)
                raise CoursePipelineError("Uploaded file has no extractable text.")

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
            file_path=saved_file_path,
            questions=generated_questions,
        )
        return course
    except FileServiceError as exc:
        delete_file_if_exists(saved_file_path)
        raise CoursePipelineError(str(exc)) from exc
    except (LLMConfigError, LLMServiceError, QuestionServiceError) as exc:
        delete_file_if_exists(saved_file_path)
        raise CoursePipelineError(str(exc)) from exc
