"""Unit tests for fusion math (no webcam / no DeepFace)."""

from app.emotion_analysis.models.signals import DeepFaceSnapshot, LandmarkMetrics
from app.emotion_analysis.services.fusion import fuse_signals


def test_fusion_happy_high_engagement():
    mp = LandmarkMetrics(
        mouth_open=0.02,
        mouth_width=0.12,
        eye_open=0.03,
        brow_raise=0.02,
        brow_asym=0.01,
        smile_signal=0.08,
        face_present=True,
    )
    df = DeepFaceSnapshot(
        dominant="happy",
        confidence=0.85,
        scores={
            "happy": 0.85,
            "neutral": 0.1,
            "angry": 0.02,
            "sad": 0.01,
            "fear": 0.01,
            "disgust": 0.0,
            "surprise": 0.01,
        },
    )
    out = fuse_signals(mp=mp, df=df, heuristic_emotion="neutral", heuristic_confidence=0.5)
    assert out.engagement > out.boredom
    assert out.stress < 0.5


def test_fusion_angry_raises_stress():
    mp = LandmarkMetrics(face_present=True, brow_asym=0.04, brow_raise=0.03, eye_open=0.02, mouth_open=0.02)
    df = DeepFaceSnapshot(
        dominant="angry",
        confidence=0.9,
        scores={"angry": 0.9, "neutral": 0.05, "happy": 0.0, "sad": 0.02, "fear": 0.02, "disgust": 0.01, "surprise": 0.0},
    )
    out = fuse_signals(mp=mp, df=df, heuristic_emotion="neutral", heuristic_confidence=0.5)
    assert out.stress > 0.4


if __name__ == "__main__":
    test_fusion_happy_high_engagement()
    test_fusion_angry_raises_stress()
    print("fusion tests: OK")
