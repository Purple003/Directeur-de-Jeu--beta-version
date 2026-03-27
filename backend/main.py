"""
Uvicorn entrypoint.

This file exists so you can run the backend from the `backend/` directory with:

    uvicorn main:app --reload

The real application lives in `backend/app/main.py`.
"""

from app.main import app  # noqa: F401
