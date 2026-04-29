from dataclasses import dataclass
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


@dataclass(frozen=True)
class AdaptedQuestionContent:
    adapted_question_text: str
    hint: str | None
    tone: str


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

    user_prompt = _build_user_prompt(
        subject=subject,
        level=level,
        description=description,
        extracted_text=extracted_text,
    )

    last_error: str | None = None
    for attempt in range(2):
        payload: dict[str, Any] = {
            "model": llm_model,
            "temperature": 0.0 if attempt > 0 else 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt if attempt == 0 else _build_repair_prompt(user_prompt, last_error)},
            ],
        }

        content = _call_llm(llm_url=llm_url, headers=headers, payload=payload)

        try:
            parsed_json = _parse_json_content_strict(content)
            questions_payload = parsed_json.get("questions")
            if not isinstance(questions_payload, list) or len(questions_payload) != 5:
                raise LLMServiceError("LLM must return exactly 5 questions in `questions`.")

            return [LLMQuestion.model_validate(item) for item in questions_payload]
        except Exception as exc:
            last_error = str(exc)
            if attempt >= 1:
                raise LLMServiceError(f"LLM output invalid JSON/schema: {last_error}") from exc
            continue

    raise LLMServiceError("LLM output invalid JSON/schema.")


def generate_wizard_dialogue(
    *,
    subject: str,
    level: str,
    description: str | None,
    extracted_text: str,
    simplify: bool = False,
) -> str:
    """
    Generates a short wizard-style explanation for a course, suitable for in-game dialogue.

    Behavior:
    - If LLM_API_KEY is missing, returns a deterministic fallback text (keeps the demo playable offline).
    - Otherwise uses the same OpenAI-compatible chat completion endpoint as question generation.
    """
    _load_env_once()
    llm_url, llm_model, llm_api_key = _get_llm_config()

    safe_subject = (subject or "").strip() or "the topic"
    safe_level = (level or "").strip() or "medium"
    safe_description = (description or "").strip()
    context = (extracted_text or "").strip()

    if not llm_api_key:
        return _fallback_wizard_dialogue(
            subject=safe_subject,
            level=safe_level,
            description=safe_description,
            simplify=bool(simplify),
        )

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_api_key}",
    }

    user_prompt = _build_dialogue_prompt(
        subject=safe_subject,
        level=safe_level,
        description=safe_description,
        extracted_text=context,
        simplify=bool(simplify),
    )

    payload: dict[str, Any] = {
        "model": llm_model,
        "temperature": 0.3 if not simplify else 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    content = _call_llm(llm_url=llm_url, headers=headers, payload=payload)
    out = (content or "").strip()
    if not out:
        return _fallback_wizard_dialogue(
            subject=safe_subject,
            level=safe_level,
            description=safe_description,
            simplify=bool(simplify),
        )
    return out


def adapt_question_presentation(
    *,
    question_text: str,
    difficulty_level: str,
    user_emotion: str | None,
    last_performance: dict[str, Any] | None = None,
) -> AdaptedQuestionContent:
    """
    Adapts presentation only:
    - keeps the DB question as the canonical source
    - never changes answer options or correct-answer logic
    - only tunes phrasing, hinting, and tone
    """
    _load_env_once()
    llm_url, llm_model, llm_api_key = _get_llm_config()

    safe_question = (question_text or "").strip()
    if not safe_question:
        raise LLMServiceError("Question text is empty.")

    safe_diff = (difficulty_level or "medium").strip().lower() or "medium"
    perf = last_performance or {}
    safe_emotion = (user_emotion or "").strip().lower() or "neutral"

    if not llm_api_key:
        return _fallback_adapted_question(
            question_text=safe_question,
            difficulty_level=safe_diff,
            user_emotion=safe_emotion,
            last_performance=perf,
        )

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_api_key}",
    }

    payload: dict[str, Any] = {
        "model": llm_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_question_adaptation_prompt(
                    question_text=safe_question,
                    difficulty_level=safe_diff,
                    user_emotion=safe_emotion,
                    last_performance=perf,
                ),
            },
        ],
    }

    content = _call_llm(llm_url=llm_url, headers=headers, payload=payload)
    try:
        parsed = _parse_json_content_strict(content)
    except Exception as exc:
        raise LLMServiceError("Question adaptation output invalid JSON.") from exc

    adapted_question_text = str(parsed.get("adapted_question_text") or "").strip()
    hint_raw = parsed.get("hint")
    tone = str(parsed.get("tone") or "").strip().lower()

    if not adapted_question_text:
        raise LLMServiceError("Question adaptation missing adapted_question_text.")
    if tone not in ("easy", "encouraging", "challenging"):
        raise LLMServiceError("Question adaptation returned invalid tone.")

    hint = str(hint_raw).strip() if hint_raw not in (None, "") else None
    return AdaptedQuestionContent(
        adapted_question_text=adapted_question_text,
        hint=hint,
        tone=tone,
    )


def _call_llm(*, llm_url: str, headers: dict[str, str], payload: dict[str, Any]) -> str:
    try:
        response = requests.post(llm_url, headers=headers, json=payload, timeout=90)
    except requests.RequestException as exc:
        raise LLMServiceError("LLM request failed (network/timeout).") from exc

    if response.status_code >= 400:
        raise LLMServiceError(_format_http_error(response))

    try:
        response_json = response.json()
        return response_json["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMServiceError("Unexpected LLM response format.") from exc


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
No markdown. No code fences. No extra text.
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


def _build_dialogue_prompt(
    *,
    subject: str,
    level: str,
    description: str,
    extracted_text: str,
    simplify: bool,
) -> str:
    limited_text = (extracted_text or "").strip()[:8000]
    style = "very simple" if simplify else "clear and motivating"

    # Keep the output human-readable (Unity will display it directly).
    return f"""You are an in-game wizard NPC guiding a student in a 2D platformer serious game.
You must explain the lesson for subject "{subject}" (level "{level}") in a {style} way.

Course description:
{description}

Course context (may be partial):
{limited_text}

Rules:
- Write between 4 and 8 short sentences total.
- No markdown, no JSON, no code fences.
- Use simple vocabulary. If simplify=true, use very short sentences and avoid jargon.
- End with ONE short sentence prompting the player to start the quiz enemies.
"""


def _build_question_adaptation_prompt(
    *,
    question_text: str,
    difficulty_level: str,
    user_emotion: str,
    last_performance: dict[str, Any],
) -> str:
    accuracy = float(last_performance.get("accuracy") or 0.0)
    avg_time_ms = last_performance.get("avg_time_ms")
    recent_correct = int(last_performance.get("recent_correct") or 0)
    recent_total = int(last_performance.get("recent_total") or 0)

    return f"""Adapt the presentation of this existing educational multiple-choice question.

Important constraints:
- Do NOT create a new question.
- Do NOT change the factual target of the question.
- Do NOT change the answer choices.
- Do NOT change which answer is correct.
- You may only rephrase the question text for clarity, and optionally add a hint.

Inputs:
- original_question_text: {question_text}
- difficulty_level: {difficulty_level}
- user_emotion: {user_emotion}
- recent_accuracy: {accuracy:.3f}
- recent_avg_time_ms: {avg_time_ms}
- recent_correct_answers: {recent_correct}
- recent_total_answers: {recent_total}

Return ONLY valid JSON with this exact shape:
{{
  "adapted_question_text": "rephrased question that preserves the same answer logic",
  "hint": "optional short hint or null",
  "tone": "easy"
}}

Rules for tone:
- "easy" for reassuring, extra-clear wording
- "encouraging" for supportive neutral wording
- "challenging" for concise, confident wording

Rules for hint:
- Keep it optional and short
- Never reveal the correct answer
- Never mention option letters

No markdown. No code fences. No extra text."""


def _fallback_wizard_dialogue(*, subject: str, level: str, description: str, simplify: bool) -> str:
    if simplify:
        base = f"Hello! Today we learn {subject}."
        if description:
            d = description.strip()
            if len(d) > 140:
                d = d[:140].rstrip() + "..."
            base += f" {d}"
        return base + " When you are ready, start the quiz enemies!"

    base = f"Greetings, adventurer! Today we explore {subject} (level: {level})."
    if description:
        d = description.strip()
        if len(d) > 220:
            d = d[:220].rstrip() + "..."
        base += f" {d}"
    return base + " If you understood, let us begin the quiz enemies!"


def _fallback_adapted_question(
    *,
    question_text: str,
    difficulty_level: str,
    user_emotion: str,
    last_performance: dict[str, Any],
) -> AdaptedQuestionContent:
    accuracy = float(last_performance.get("accuracy") or 0.0)
    tone = "encouraging"
    hint: str | None = None

    if difficulty_level == "hard" and accuracy >= 0.75 and user_emotion in ("focused", "engaged", "happy"):
        tone = "challenging"
    elif difficulty_level == "easy" or user_emotion in ("frustrated", "stress", "stressed", "confused", "sad"):
        tone = "easy"

    if tone == "easy":
        hint = "Take it step by step and look for the key concept in the question."
    elif tone == "encouraging":
        hint = "Focus on the main idea before comparing the answer choices."

    return AdaptedQuestionContent(
        adapted_question_text=question_text,
        hint=hint,
        tone=tone,
    )


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


def _parse_json_content_strict(content: str) -> dict[str, Any]:
    """
    STRICT mode:
    - The model must return ONLY a JSON object (no code fences, no extra text).
    - Any deviation is treated as an error (and triggers at most one retry).
    """
    cleaned = (content or "").strip()
    if not cleaned:
        raise LLMServiceError("LLM returned empty content.")
    if "```" in cleaned:
        raise LLMServiceError("LLM returned code fences; strict JSON required.")
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        raise LLMServiceError("LLM returned non-JSON content; strict JSON required.")

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMServiceError("LLM returned invalid JSON.") from exc

    if not isinstance(parsed, dict):
        raise LLMServiceError("LLM JSON root must be an object.")

    return parsed


def _build_repair_prompt(original_prompt: str, error: str | None) -> str:
    # Intentionally do NOT include the previous model output to avoid prompt bloat/leaks.
    err = (error or "").strip()
    return (
        original_prompt
        + "\n\nYour previous response was INVALID.\n"
        + (f"Reason: {err}\n" if err else "")
        + "Return ONLY a single JSON object. No markdown. No backticks. No extra keys.\n"
    )


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
