from __future__ import annotations

import logging

import numpy as np

from ..models.signals import AnalysisResult, DeepFaceSnapshot, LandmarkMetrics
from .deepface_service import DeepFaceEmotionRunner
from .fusion import fuse_signals_safe
from .mediapipe_service import MediaPipeLandmarkService

logger = logging.getLogger(__name__)


class EmotionOrchestrator:
    """
    Per-frame pipeline:
    1) MediaPipe (fast) always runs when OpenCV decode succeeds.
    2) DeepFace (slow) runs in a worker thread only when a face mesh is present.
    3) Fusion combines both + heuristic fallbacks.
    """

    def __init__(
        self,
        *,
        mediapipe: MediaPipeLandmarkService | None = None,
        deepface: DeepFaceEmotionRunner | None = None,
    ) -> None:
        self._mp = mediapipe or MediaPipeLandmarkService()
        self._df = deepface or DeepFaceEmotionRunner()

    def analyze_bgr(self, img_bgr: np.ndarray | None, *, emotion_hint: str | None = None) -> AnalysisResult:
        if img_bgr is None or img_bgr.size == 0:
            return self._hint_only(emotion_hint)

        mp_metrics = self._mp.extract_metrics(img_bgr)
        h_label, h_conf = self._mp.heuristic_emotion(mp_metrics)

        df_snap: DeepFaceSnapshot | None = None
        # DeepFace is completely bypassed for real-time Web performance
        # if mp_metrics.face_present:
        #     try:
        #         df_snap = self._df.analyze(img_bgr)
        #     except Exception as exc:
        #         logger.warning("[Orchestrator] DeepFace error (ignored): %s", exc)

        merged = fuse_signals_safe(mp=mp_metrics, df=df_snap, heuristic_emotion=h_label, heuristic_confidence=h_conf)
        if emotion_hint and not mp_metrics.face_present:
            merged = self._merge_hint(merged, emotion_hint)
        return merged

    def analyze_bytes(self, image_bytes: bytes | None, *, emotion_hint: str | None = None) -> AnalysisResult:
        if not image_bytes:
            return self._hint_only(emotion_hint)
        try:
            import cv2  # type: ignore
        except Exception as exc:
            logger.error("[Orchestrator] OpenCV required for frame decode: %s", exc)
            return self._hint_only(emotion_hint)

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            logger.warning("[Orchestrator] imdecode failed")
            return self._hint_only(emotion_hint)
        return self.analyze_bgr(img_bgr, emotion_hint=emotion_hint)

    def _hint_only(self, emotion_hint: str | None) -> AnalysisResult:
        if emotion_hint:
            h = str(emotion_hint).strip().lower()
            return fuse_signals_safe(
                mp=LandmarkMetrics(),
                df=None,
                heuristic_emotion=h,
                heuristic_confidence=0.65,
            )
        return fuse_signals_safe(
            mp=LandmarkMetrics(),
            df=None,
            heuristic_emotion="neutral",
            heuristic_confidence=0.5,
        )

    def _merge_hint(self, merged: AnalysisResult, emotion_hint: str) -> AnalysisResult:
        """Bias toward client hint when the camera does not see a face."""
        hint = str(emotion_hint).lower().strip()
        if not hint:
            return merged
        emotions = dict(merged.emotions)
        emotions[hint] = max(0.35, emotions.get(hint, 0.0), merged.confidence * 0.5)
        return AnalysisResult(
            emotion=hint,
            confidence=max(merged.confidence, 0.55),
            stress=merged.stress * 0.85,
            engagement=max(merged.engagement, 0.45),
            boredom=merged.boredom * 0.9,
            emotions=emotions,
            mediapipe=merged.mediapipe,
            deepface_dominant=merged.deepface_dominant,
            deepface_fresh=merged.deepface_fresh,
        )

    def close(self) -> None:
        self._mp.close()
        self._df.shutdown()
