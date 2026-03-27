from __future__ import annotations

import logging
from typing import Mapping

from ..models.signals import AnalysisResult, DeepFaceSnapshot, LandmarkMetrics

logger = logging.getLogger(__name__)

_SCORE_KEYS = ("angry", "disgust", "fear", "happy", "sad", "surprise", "neutral")


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _score_get(scores: Mapping[str, float], key: str) -> float:
    for k, v in scores.items():
        if str(k).lower() == key:
            return _clamp01(float(v))
    return 0.0


def fuse_signals(
    *,
    mp: LandmarkMetrics | None,
    df: DeepFaceSnapshot | None,
    heuristic_emotion: str,
    heuristic_confidence: float,
) -> AnalysisResult:
    """
    Combines MediaPipe geometry with DeepFace probabilities (when present).

    stress / engagement / boredom are in [0, 1] for game adaptation curves.
    """
    mp = mp or LandmarkMetrics()
    emotions: dict[str, float] = {k: 0.0 for k in _SCORE_KEYS}

    if df and df.scores:
        for k in _SCORE_KEYS:
            emotions[k] = _score_get(df.scores, k)
    else:
        # Soft clues from heuristic label when DeepFace is offline / throttled.
        h = heuristic_emotion.lower()
        if h == "happy":
            emotions["happy"] = heuristic_confidence
            emotions["neutral"] = 1.0 - heuristic_confidence
        elif h == "focused":
            emotions["neutral"] = 0.55
            emotions["happy"] = 0.25
        elif h == "frustrated":
            emotions["angry"] = heuristic_confidence * 0.7
            emotions["sad"] = heuristic_confidence * 0.3
        elif h == "confused":
            emotions["surprise"] = heuristic_confidence * 0.5
            emotions["neutral"] = 0.5
        else:
            emotions["neutral"] = max(heuristic_confidence, 0.55)

    n = emotions["neutral"]
    ha = emotions["happy"]
    an = emotions["angry"]
    sa = emotions["sad"]
    fe = emotions["fear"]
    di = emotions["disgust"]
    su = emotions["surprise"]

    # --- Derived axes
    stress = _clamp01(0.38 * an + 0.22 * sa + 0.22 * fe + 0.18 * di + 0.12 * (1.0 - ha))
    engagement = _clamp01(0.42 * ha + 0.28 * su + 0.22 * (1.0 - n) + 0.12 * ha)

    smile_norm = _clamp01((mp.smile_signal - 0.02) / 0.08) if mp.face_present else 0.0
    eye_norm = _clamp01((mp.eye_open - 0.015) / 0.025) if mp.face_present else 0.0
    mp_activity = _clamp01(0.5 * smile_norm + 0.5 * eye_norm)

    boredom = _clamp01(0.5 * n + 0.3 * (1.0 - mp_activity) + 0.2 * (1.0 - su - ha))

    if mp.face_present:
        stress += 0.18 * _clamp01((mp.brow_asym - 0.02) / 0.05)
        if mp.brow_raise < 0.012 and mp.eye_open < 0.018:
            stress += 0.08
        engagement += 0.12 * mp_activity
        boredom -= 0.08 * mp_activity

    stress = _clamp01(stress)
    engagement = _clamp01(engagement)
    boredom = _clamp01(boredom)

    if df and df.dominant:
        api_emotion = df.dominant
        confidence = df.confidence
    else:
        api_emotion = heuristic_emotion
        confidence = heuristic_confidence

    api_emotion, confidence = _map_api_emotion(api_emotion, confidence)

    mp_debug = {}
    if mp.face_present:
        mp_debug = {
            "mouth_open": round(mp.mouth_open, 4),
            "mouth_width": round(mp.mouth_width, 4),
            "eye_open": round(mp.eye_open, 4),
            "brow_raise": round(mp.brow_raise, 4),
            "brow_asym": round(mp.brow_asym, 4),
            "smile_signal": round(mp.smile_signal, 4),
        }

    return AnalysisResult(
        emotion=api_emotion,
        confidence=_clamp01(confidence),
        stress=stress,
        engagement=engagement,
        boredom=boredom,
        emotions={k: round(float(v), 4) for k, v in emotions.items()},
        mediapipe=mp_debug,
        deepface_dominant=df.dominant if df else None,
        deepface_fresh=bool(df and df.is_fresh),
    )


def _map_api_emotion(label: str, confidence: float) -> tuple[str, float]:
    """
    Map classifier labels to the compact set used by gameplay + DB.
    """
    e = (label or "").strip().lower()
    if not e:
        return "neutral", 0.5
    if e in ("happy", "sad", "angry", "neutral"):
        return e, confidence
    if e in ("surprise", "surprised"):
        return "surprised", confidence
    if e in ("fear", "disgust"):
        return "neutral", confidence * 0.9
    if e in ("focused", "confused", "frustrated"):
        return e, confidence
    return "neutral", 0.55


def fuse_signals_safe(
    *,
    mp: LandmarkMetrics | None,
    df: DeepFaceSnapshot | None,
    heuristic_emotion: str,
    heuristic_confidence: float,
) -> AnalysisResult:
    """Never raises; returns neutral fusion on failure."""
    try:
        return fuse_signals(mp=mp, df=df, heuristic_emotion=heuristic_emotion, heuristic_confidence=heuristic_confidence)
    except Exception as exc:
        logger.exception("[Fusion] failed, neutral fallback: %s", exc)
        return AnalysisResult(
            emotion="neutral",
            confidence=0.5,
            stress=0.35,
            engagement=0.35,
            boredom=0.45,
            emotions={k: (1.0 if k == "neutral" else 0.0) for k in _SCORE_KEYS},
            mediapipe={},
            deepface_dominant=None,
            deepface_fresh=False,
        )
