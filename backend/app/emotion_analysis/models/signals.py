from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LandmarkMetrics:
    """Normalized MediaPipe FaceMesh geometry (0..1-ish in image space)."""

    mouth_open: float = 0.0
    mouth_width: float = 0.0
    eye_open: float = 0.0
    brow_raise: float = 0.0
    brow_asym: float = 0.0
    smile_signal: float = 0.0
    face_present: bool = False


@dataclass
class DeepFaceSnapshot:
    """One DeepFace emotion prediction (or a cached / throttled view)."""

    dominant: str
    confidence: float
    scores: dict[str, float]
    is_fresh: bool = True
    error: str | None = None


@dataclass
class AnalysisResult:
    """Fused output suitable for game clients (Unity) and REST JSON."""

    emotion: str
    confidence: float
    stress: float
    engagement: float
    boredom: float
    emotions: dict[str, float] = field(default_factory=dict)
    mediapipe: dict[str, float] = field(default_factory=dict)
    deepface_dominant: str | None = None
    deepface_fresh: bool = False
