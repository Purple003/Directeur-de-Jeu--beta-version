import re
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from PyPDF2 import PdfReader
from docx import Document

# backend/app/services -> parents[2] == backend/
BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


class FileServiceError(Exception):
    """Raised when file operations fail."""


def save_uploaded_file(file: UploadFile) -> str:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise FileServiceError("Only PDF and DOCX files are allowed.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    original_stem = Path(file.filename or "uploaded_file").stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", original_stem)[:80] or "uploaded_file"
    destination = UPLOAD_DIR / f"{safe_stem}_{uuid.uuid4().hex}{extension}"

    try:
        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        raise FileServiceError("Failed to save uploaded file.") from exc
    finally:
        try:
            file.file.close()
        except Exception:
            pass

    # Store relative path (from backend/) for portability.
    return str(destination.relative_to(BASE_DIR))


def extract_text(relative_file_path: str) -> str:
    path = (BASE_DIR / relative_file_path).resolve()
    extension = path.suffix.lower()

    try:
        if extension == ".pdf":
            return _extract_pdf_text(path)
        if extension == ".docx":
            return _extract_docx_text(path)
    except Exception as exc:
        raise FileServiceError("Failed to extract text from file.") from exc

    raise FileServiceError("Unsupported file type.")


def delete_file_if_exists(relative_file_path: str | None) -> None:
    if not relative_file_path:
        return
    path = (BASE_DIR / relative_file_path).resolve()
    if path.exists():
        path.unlink(missing_ok=True)


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _extract_docx_text(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs).strip()
