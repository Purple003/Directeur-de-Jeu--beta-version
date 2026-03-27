"""
Real-time emotion analysis pipeline (MediaPipe + DeepFace + fusion).

Layers:
- models/: plain dataclasses / DTOs (no ML imports)
- services/: detection runners and fusion logic
"""

from .models.signals import (
    AnalysisResult,
    DeepFaceSnapshot,
    LandmarkMetrics,
)
from .services.orchestrator import EmotionOrchestrator

__all__ = [
    "AnalysisResult",
    "DeepFaceSnapshot",
    "EmotionOrchestrator",
    "LandmarkMetrics",
]
