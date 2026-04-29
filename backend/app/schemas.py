from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class ApiError(BaseModel):
    message: str
    details: Any | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ApiError | None = None


class CourseCreateResponse(BaseModel):
    message: str
    course_id: int


class GenerateQuestionsRequest(BaseModel):
    difficulty: str | None = Field(default=None, description="easy|medium|hard")


class GenerateQuestionsResponse(BaseModel):
    message: str
    course_id: int
    created: int


class LLMQuestion(BaseModel):
    question: str = Field(..., min_length=1)
    choices: list[str] = Field(..., min_length=4, max_length=4)
    correct_answer: str = Field(..., min_length=1)
    difficulty_level: str = Field(..., min_length=1)

    @field_validator("correct_answer")
    @classmethod
    def _correct_answer_letter(cls, v: str) -> str:
        vv = (v or "").strip().upper()
        if vv not in ("A", "B", "C", "D"):
            raise ValueError("correct_answer must be one of: A, B, C, D")
        return vv

    @field_validator("difficulty_level")
    @classmethod
    def _difficulty_enum(cls, v: str) -> str:
        vv = (v or "").strip().lower()
        if vv not in ("easy", "medium", "hard"):
            raise ValueError("difficulty_level must be one of: easy, medium, hard")
        return vv

    @field_validator("choices")
    @classmethod
    def _choices_len(cls, v: list[str]) -> list[str]:
        if not isinstance(v, list) or len(v) != 4:
            raise ValueError("choices must be a list of exactly 4 strings")
        out = [str(x) for x in v]
        if any(not s.strip() for s in out):
            raise ValueError("choices must not contain empty strings")
        return out


class CourseQuestionsResponseItem(BaseModel):
    id: int
    course_id: int
    question: str
    choices: list[str]
    correct_answer: str
    difficulty_level: str


class CourseQuestionsResponse(BaseModel):
    course_id: int
    questions: list[CourseQuestionsResponseItem]


class PlayerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    age: int | None = Field(default=None, ge=3, le=120)
    school_level: str | None = Field(default=None, max_length=64)
    experience_level: str | None = Field(default=None, max_length=64)


class PlayerCreateResponse(BaseModel):
    message: str
    player_id: int


class PlayerProfile(BaseModel):
    id: int
    name: str
    age: int | None = None
    school_level: str | None = None
    experience_level: str | None = None
    game_level: int | None = None
    xp: int | None = None
    stars: int | None = None


class PlayerUpdateRequest(BaseModel):
    player_id: int
    name: str | None = Field(default=None, min_length=1, max_length=255)
    age: int | None = Field(default=None, ge=3, le=120)
    school_level: str | None = Field(default=None, max_length=64)
    experience_level: str | None = Field(default=None, max_length=64)


class PlayerUpdateResponse(BaseModel):
    message: str
    player: PlayerProfile


class SubmitScoreRequest(BaseModel):
    player_id: int
    course_id: int
    score: float = Field(..., ge=0, le=100)
    emotion_score: float | None = Field(default=None, ge=0, le=100)
    emotion_state: str | None = None


class SubmitScoreResponse(BaseModel):
    message: str
    recommended_difficulty: str
    progress_id: int


class GameQuestionItem(BaseModel):
    id: int
    course_id: int
    question: str
    choices: list[str]
    correct_answer: str
    difficulty_level: str
    hint: str | None = None
    tone: str | None = None


class GameQuestionsResponse(BaseModel):
    course_id: int
    recommended_difficulty: str | None = None
    questions: list[GameQuestionItem]


class StartSessionRequest(BaseModel):
    player_id: int = Field(..., ge=1, description="Player id (positive integer)")
    course_id: int = Field(..., ge=1, description="Course id (positive integer)")


class StartSessionResponse(BaseModel):
    message: str
    session_id: int
    recommended_difficulty: str | None = None
    next_question: GameQuestionItem | None = None


class NextQuestionResponse(BaseModel):
    session_id: int
    course_id: int
    player_level: int
    recommended_difficulty: str
    question: GameQuestionItem | None = None
    remaining_in_difficulty: int
    remaining_total: int


class GenerateDialogueRequest(BaseModel):
    session_id: int = Field(..., ge=1, description="Session id (positive integer)")
    course_id: int = Field(..., ge=1, description="Course id (positive integer)")
    simplify: bool = Field(default=False, description="If true, generate a simpler explanation")


class GenerateDialogueResponse(BaseModel):
    session_id: int
    course_id: int
    simplified: bool
    dialogue_text: str


class SubmitAnswerRequest(BaseModel):
    session_id: int = Field(..., ge=1, description="Session id (positive integer)")
    question_id: int = Field(..., ge=1, description="Question id (positive integer)")
    selected_answer: str = Field(..., min_length=1, max_length=255)
    time_spent_ms: int | None = Field(default=None, ge=0)
    emotion: str | None = Field(default=None, max_length=64)
    confidence: float | None = Field(default=None, ge=0, le=1)


class SubmitAnswerResponse(BaseModel):
    message: str
    is_correct: bool


class ProgressionState(BaseModel):
    player_id: int
    course_id: int
    level: int
    recommended_difficulty: str


class UpdateProgressRequest(BaseModel):
    player_id: int
    xp_delta: int = Field(default=0)
    stars_delta: int = Field(default=0)


class UpdateProgressResponse(BaseModel):
    message: str
    player_id: int
    xp: int
    stars: int
    game_level: int


class EndSessionRequest(BaseModel):
    session_id: int = Field(..., ge=1, description="Session id (positive integer)")
    final_score: float | None = Field(default=None, ge=0, le=100)


class EndSessionResponse(BaseModel):
    message: str
    session_id: int
    final_score: float
    duration_ms: int | None = None
    next_level: int | None = None
    recommended_difficulty: str | None = None


class StudentProgressResponse(BaseModel):
    player_id: int
    total_sessions: int
    total_answers: int
    correct_answers: int
    accuracy: float


class CourseResultsResponse(BaseModel):
    course_id: int
    total_sessions: int
    total_answers: int
    correct_answers: int
    accuracy: float


class EmotionRequest(BaseModel):
    """JSON body for POST /emotion/analyze-detailed (application/json)."""

    session_id: str = Field(..., description="Game session id (numeric string, e.g. '42')")
    question_id: str | None = Field(default=None, description="Optional question id (numeric string)")
    emotion_hint: str | None = Field(default=None, max_length=64)

    @field_validator("session_id", mode="before")
    @classmethod
    def _coerce_session_id(cls, v: object) -> str:
        if v is None:
            raise ValueError("session_id is required")
        return str(v).strip()

    @field_validator("question_id", mode="before")
    @classmethod
    def _coerce_question_id(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip()


# Backward-compatible alias (same shape: session_id is now string-coerced).
EmotionAnalyzeRequest = EmotionRequest


class EmotionAnalyzeSimpleRequest(BaseModel):
    """JSON body for POST /emotion/analyze (simple state)."""

    session_id: str = Field(..., description="Game session id (numeric string, e.g. '42')")
    image_base64: str | None = Field(
        default=None,
        description="Optional image as base64 (raw base64 or data URL).",
    )
    emotion_hint: str | None = Field(default=None, max_length=64, description="Optional hint if image is missing/unusable")
    question_id: str | None = Field(default=None, description="Optional question id (numeric string)")
    store: bool = Field(default=True, description="If true, store result in DB (non-blocking).")

    @field_validator("session_id", mode="before")
    @classmethod
    def _coerce_session_id(cls, v: object) -> str:
        if v is None:
            raise ValueError("session_id is required")
        return str(v).strip()

    @field_validator("question_id", mode="before")
    @classmethod
    def _coerce_question_id(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip()


class EmotionStateResponse(BaseModel):
    state: str = Field(..., description="calm | engaged | stressed")
    confidence: float = Field(..., ge=0.0, le=1.0)


class EmotionAnalyzeResponse(BaseModel):
    emotion: str
    confidence: float
    stress: float = Field(ge=0.0, le=1.0, description="Estimated cognitive/affective stress [0,1]")
    engagement: float = Field(ge=0.0, le=1.0, description="Attention / positive activation [0,1]")
    boredom: float = Field(ge=0.0, le=1.0, description="Disengagement proxy [0,1]")
    emotions: dict[str, float] = Field(default_factory=dict, description="Normalized DeepFace axis scores (approx. [0,1])")
    mediapipe_signals: dict[str, float] | None = Field(
        default=None, description="Optional FaceMesh geometry (for tuning / debug)"
    )
    deepface_fresh: bool = Field(default=False, description="True if DeepFace ran on this frame (not cached / throttled)")
