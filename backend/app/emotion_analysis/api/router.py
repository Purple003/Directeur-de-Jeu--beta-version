"""
REST endpoints for real-time emotion / engagement fusion.

POST /emotion/analyze accepts:
- application/json → EmotionRequest
- multipart/form-data → session_id, optional question_id, emotion_hint, optional frame file

OpenAPI documents both body styles on the same operation via `openapi_extra`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import (
    ApiResponse,
    EmotionAnalyzeResponse,
    EmotionAnalyzeSimpleRequest,
    EmotionRequest,
    EmotionStateResponse,
)
from ...services.emotion_service import analyze_emotion_detailed, store_emotion
from ...services.emotion_state_service import analyze_emotion_state
from ...utils.api_response import ok

router = APIRouter(prefix="/emotion", tags=["Emotion"])


def _emotion_analyze_openapi_extra() -> dict:
    """Expose JSON + multipart in OpenAPI (Swagger) for the same path."""
    return {
        "requestBody": {
            "description": (
                "Use **application/json** (schema: EmotionRequest) "
                "or **multipart/form-data** (fields + optional `frame` file)."
            ),
            "required": True,
            "content": {
                "application/json": {
                    "schema": EmotionRequest.model_json_schema(),
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["session_id"],
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "title": "session_id",
                                "description": "Game session id (numeric string)",
                            },
                            "question_id": {
                                "type": "string",
                                "nullable": True,
                                "description": "Optional question id (numeric string)",
                            },
                            "emotion_hint": {
                                "type": "string",
                                "nullable": True,
                                "description": "Optional emotion hint",
                            },
                            "frame": {
                                "type": "string",
                                "format": "binary",
                                "description": "Optional camera frame (jpeg/png)",
                            },
                        },
                    }
                },
            },
        }
    }


def _emotion_state_openapi_extra() -> dict:
    """Expose JSON + multipart in OpenAPI (Swagger) for the state endpoint."""
    return {
        "requestBody": {
            "description": (
                "Use **application/json** (schema: EmotionAnalyzeSimpleRequest) "
                "or **multipart/form-data** (fields + optional `image` file)."
            ),
            "required": True,
            "content": {
                "application/json": {"schema": EmotionAnalyzeSimpleRequest.model_json_schema()},
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["session_id"],
                        "properties": {
                            "session_id": {"type": "string", "description": "Game session id (numeric string)"},
                            "question_id": {"type": "string", "nullable": True},
                            "emotion_hint": {"type": "string", "nullable": True},
                            "image_base64": {"type": "string", "nullable": True},
                            "store": {"type": "boolean", "nullable": True, "description": "Store result in DB (default true)"},
                            "image": {"type": "string", "format": "binary", "description": "Optional camera frame (jpeg/png)"},
                            "frame": {"type": "string", "format": "binary", "description": "Alias for image"},
                        },
                    }
                },
            },
        }
    }


def _session_id_to_int(session_id: str) -> int:
    try:
        sid = int(str(session_id).strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="session_id must be a numeric string.",
        ) from exc
    if sid <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="session_id must be a positive integer.",
        )
    return sid


def _optional_question_id_to_int(raw: str | None) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="question_id must be a numeric string.",
        ) from exc


async def _parse_analyze_request(request: Request) -> tuple[int, int | None, str | None, bytes | None]:
    """
    Returns (session_id_int, question_id, emotion_hint, image_bytes).
    """
    content_type = (request.headers.get("content-type") or "").lower()
    image_bytes: bytes | None = None

    if content_type.startswith("application/json"):
        try:
            body = EmotionRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        sid = _session_id_to_int(body.session_id)
        qid = _optional_question_id_to_int(body.question_id)
        return sid, qid, body.emotion_hint, None

    form = await request.form()
    raw_sid = form.get("session_id")
    if raw_sid is None or str(raw_sid).strip() == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="session_id is required.",
        )
    sid = _session_id_to_int(str(raw_sid))
    raw_qid = form.get("question_id")
    qid = _optional_question_id_to_int(str(raw_qid)) if raw_qid not in (None, "") else None
    raw_hint = form.get("emotion_hint")
    hint = str(raw_hint).strip() if raw_hint not in (None, "") else None

    frame = form.get("frame")
    if frame is not None and hasattr(frame, "read"):
        image_bytes = await frame.read()

    return sid, qid, hint, image_bytes


@router.post(
    "/analyze-detailed",
    response_model=ApiResponse[EmotionAnalyzeResponse],
    status_code=status.HTTP_200_OK,
    summary="Analyze emotion (detailed fusion output)",
    description=(
        "**JSON:** set `Content-Type: application/json` and send `EmotionRequest`.\n\n"
        "**Multipart:** `multipart/form-data` with fields `session_id` (required), "
        "`question_id`, `emotion_hint`, and optional file `frame`.\n\n"
        "Swagger: open **Request body** and pick the media type tab (json vs multipart)."
    ),
    openapi_extra=_emotion_analyze_openapi_extra(),
)
async def emotion_analyze_detailed(request: Request, db: Session = Depends(get_db)):
    """
    Single entry point: branches on Content-Type. Uses `analyze_emotion_detailed` (fusion pipeline).
    """
    session_id, question_id, emotion_hint, image_bytes = await _parse_analyze_request(request)

    out = analyze_emotion_detailed(emotion_hint=emotion_hint, image_bytes=image_bytes)

    store_emotion(
        db,
        session_id=session_id,
        question_id=question_id,
        emotion=out.emotion,
        confidence=out.confidence,
    )

    mp = out.mediapipe if out.mediapipe else None
    body = EmotionAnalyzeResponse(
        emotion=out.emotion,
        confidence=out.confidence,
        stress=out.stress,
        engagement=out.engagement,
        boredom=out.boredom,
        emotions=out.emotions,
        mediapipe_signals=mp,
        deepface_fresh=out.deepface_fresh,
    )
    return ok(body.model_dump())


async def _parse_state_request(
    request: Request,
) -> tuple[int, int | None, str | None, bytes | None, str | None, bool]:
    """
    Returns (session_id_int, question_id, emotion_hint, image_bytes, image_base64, store).
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if content_type.startswith("application/json"):
        try:
            body = EmotionAnalyzeSimpleRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        sid = _session_id_to_int(body.session_id)
        qid = _optional_question_id_to_int(body.question_id)
        return sid, qid, body.emotion_hint, None, body.image_base64, bool(body.store)

    form = await request.form()
    raw_sid = form.get("session_id")
    if raw_sid is None or str(raw_sid).strip() == "":
        raise HTTPException(status_code=422, detail="session_id is required.")
    sid = _session_id_to_int(str(raw_sid))

    raw_qid = form.get("question_id")
    qid = _optional_question_id_to_int(str(raw_qid)) if raw_qid not in (None, "") else None

    raw_hint = form.get("emotion_hint")
    hint = str(raw_hint).strip() if raw_hint not in (None, "") else None

    store_raw = form.get("store")
    store_val = True
    if store_raw not in (None, ""):
        store_val = str(store_raw).strip().lower() not in ("0", "false", "no", "off")

    image_bytes: bytes | None = None
    image_b64: str | None = None

    raw_b64 = form.get("image_base64")
    if raw_b64 not in (None, ""):
        image_b64 = str(raw_b64).strip()

    upload = form.get("image") or form.get("frame")
    if upload is not None and hasattr(upload, "read"):
        image_bytes = await upload.read()

    return sid, qid, hint, image_bytes, image_b64, store_val


@router.post(
    "/analyze",
    response_model=EmotionStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze emotion (simple gameplay state)",
    description=(
        "Returns a simple gameplay state: `calm | engaged | stressed`.\n\n"
        "Server enforces a per-session minimum interval (default: 60 seconds) to avoid continuous detection."
    ),
    openapi_extra=_emotion_state_openapi_extra(),
)
async def emotion_analyze_state(request: Request, db: Session = Depends(get_db)):
    session_id, question_id, emotion_hint, image_bytes, image_b64, store = await _parse_state_request(request)

    state, confidence = analyze_emotion_state(
        db,
        session_id=session_id,
        question_id=question_id,
        image_bytes=image_bytes,
        image_base64=image_b64,
        emotion_hint=emotion_hint,
        store=store,
    )
    return EmotionStateResponse(state=state, confidence=float(confidence))
