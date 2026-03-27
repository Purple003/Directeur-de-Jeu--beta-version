import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values

from ..schemas import LLMQuestion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are an adaptive educational AI system."

_ENV_LOADED = False


class LLMServiceError(Exception):
    """Raised when LLM processing fails."""


class LLMConfigError(LLMServiceError):
    """Raised when server-side LLM configuration is missing/invalid."""


def generate_mcq_questions(
    *,
    subject: str,
    level: str,
    description: str | None,
    extracted_text: str,
) -> list[LLMQuestion]:
    """
    OpenAI-compatible Chat Completions call.

    Loads `.env` from:
    - DOTENV_PATH (optional explicit path)
    - backend/.env
    - repo-root/.env

    Variables:
    - LLM_API_URL (default: Groq OpenAI-compatible endpoint)
    - LLM_MODEL (default: a Groq-friendly model name)
    - LLM_API_KEY (required for cloud providers like Groq)
    """
    _load_env_once()
    llm_url, llm_model, llm_api_key = _get_llm_config()

    # Production-safe debug logging: never print secrets, only presence.
    logger.debug(
        "LLM config: url=%s model=%s api_key_set=%s",
        llm_url,
        llm_model,
        bool(llm_api_key),
    )

    if not llm_api_key:
        raise LLMConfigError(_missing_key_message())

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_api_key}",
    }

    payload: dict[str, Any] = {
        "model": llm_model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(
                    subject=subject,
                    level=level,
                    description=description,
                    extracted_text=extracted_text,
                ),
            },
        ],
    }

    try:
        response = requests.post(llm_url, headers=headers, json=payload, timeout=90)
    except requests.RequestException as exc:
        raise LLMServiceError("LLM request failed (network/timeout).") from exc

    if response.status_code >= 400:
        raise LLMServiceError(_format_http_error(response))

    try:
        response_json = response.json()
        content = response_json["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMServiceError("Unexpected LLM response format.") from exc

    parsed_json = _parse_json_content(content)
    questions_payload = parsed_json.get("questions")
    if not isinstance(questions_payload, list) or len(questions_payload) != 5:
        raise LLMServiceError("LLM must return exactly 5 questions.")

    try:
        return [LLMQuestion.model_validate(item) for item in questions_payload]
    except Exception as exc:
        raise LLMServiceError("LLM output failed schema validation.") from exc


def _load_env_once() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    repo_root = Path(__file__).resolve().parents[3]
    backend_dir = Path(__file__).resolve().parents[2]

    explicit = os.getenv("DOTENV_PATH")
    candidate_paths: list[Path] = []
    if explicit:
        candidate_paths.append(Path(explicit).expanduser())
    candidate_paths.append(backend_dir / ".env")
    candidate_paths.append(repo_root / ".env")

    for p in candidate_paths:
        exists = p.exists()
        if not exists:
            logger.debug("dotenv check: path=%s exists=%s", str(p), exists)
            continue

        # Only fill missing/empty env vars; do not override non-empty process env.
        values = dotenv_values(p)
        set_any = False
        for key, value in values.items():
            if value is None:
                continue
            current = os.getenv(key)
            if current is None or current == "":
                os.environ[key] = str(value)
                set_any = True
                # Never log values (secrets), only keys.
                logger.debug("dotenv set: key=%s (from %s)", key, str(p))

        logger.debug("dotenv check: path=%s exists=%s applied=%s", str(p), exists, set_any)

    _ENV_LOADED = True


def _get_llm_config() -> tuple[str, str, str | None]:
    llm_url = (
        os.getenv("LLM_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
    )
    llm_model = os.getenv("LLM_MODEL", "llama-3.1-8b-instant").strip()
    llm_api_key_raw = os.getenv("LLM_API_KEY")
    llm_api_key = llm_api_key_raw.strip() if llm_api_key_raw else None
    return llm_url, llm_model, llm_api_key


def _build_user_prompt(
    *,
    subject: str,
    level: str,
    description: str | None,
    extracted_text: str,
) -> str:
    safe_description = (description or "").strip()
    limited_text = (extracted_text or "").strip()[:15000]
    suggested = _suggest_difficulty(level)

    return f"""Generate educational quiz questions for subject "{subject}" at level "{level}".

Context (may be partial):
{safe_description}
{limited_text}

Generate exactly 5 multiple choice questions.
Rules:
- Questions must be strictly about the subject "{subject}".
- Each question must have exactly 4 choices.
- correct_answer must be one of: "A", "B", "C", "D" (the letter matching the correct choice).
- difficulty_level must be one of: "easy", "medium", "hard".
  Use: beginner->easy, intermediate->medium, advanced->hard.
  For this course, set difficulty_level="{suggested}" for all questions.

Return ONLY valid JSON with this shape:
{{
  "questions": [
    {{
      "question": "...",
      "choices": ["...", "...", "...", "..."],
      "correct_answer": "A",
      "difficulty_level": "{suggested}"
    }}
  ]
}}"""


def _suggest_difficulty(level: str) -> str:
    v = (level or "").strip().lower()
    if v in ("easy", "medium", "hard"):
        return v
    if v == "beginner":
        return "easy"
    if v == "intermediate":
        return "medium"
    if v == "advanced":
        return "hard"
    return "medium"


def _parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Tolerate extra text by extracting the first JSON object.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMServiceError("LLM returned non-JSON content.")
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMServiceError("LLM returned non-JSON content.") from exc

    if not isinstance(parsed, dict):
        raise LLMServiceError("LLM JSON root must be an object.")

    return parsed


def _format_http_error(response: requests.Response) -> str:
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                detail = str(err.get("message") or err.get("detail") or "")
            elif "message" in payload:
                detail = str(payload.get("message") or "")
    except Exception:
        pass

    if not detail:
        text = (response.text or "").strip()
        detail = text[:300] if text else "No response body."

    return f"LLM service returned HTTP {response.status_code}: {detail}"


def _missing_key_message() -> str:
    backend_dir = Path(__file__).resolve().parents[2]
    dotenv_path = backend_dir / ".env"
    if dotenv_path.exists() and dotenv_path.stat().st_size == 0:
        env_hint = "I found `backend/.env` but it is empty (0 bytes)."
    elif dotenv_path.exists():
        env_hint = "I found `backend/.env` but it does not contain LLM_API_KEY."
    else:
        env_hint = "I did not find `backend/.env`."

    return (
        f"Missing LLM_API_KEY. {env_hint} "
        "Add it to `backend/.env` (recommended) or set it for the current PowerShell "
        "session with `$env:LLM_API_KEY=\"...\"`. If you used `setx`, restart the "
        "terminal so the new variable is visible."
    )
