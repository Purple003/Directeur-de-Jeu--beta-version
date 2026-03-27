from __future__ import annotations

import logging
from typing import Any

import numpy as np

from ..models.signals import LandmarkMetrics

logger = logging.getLogger(__name__)


class MediaPipeLandmarkService:
    """
    Fast path: FaceMesh landmarks → geometric features + optional heuristic mood label.

    FaceMesh instances are not thread-safe; use one instance per consumer thread/worker.
    """

    def __init__(self) -> None:
        self._mesh: Any | None = None
        self._state: str = "unknown"
        self._logged_ok = False
        self._logged_fail = False

    def _ensure_mesh(self) -> Any | None:
        if self._mesh is not None:
            return self._mesh
        if self._state in ("missing", "failed"):
            return None
        try:
            import mediapipe as mp  # type: ignore
        except Exception as exc:
            self._state = "missing"
            if not self._logged_fail:
                self._logged_fail = True
                logger.error("[MediaPipe] package missing: %s", exc)
            return None
        try:
            self._mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._state = "ok"
            if not self._logged_ok:
                self._logged_ok = True
                logger.info("[MediaPipe] FaceMesh initialized")
            return self._mesh
        except Exception as exc:
            self._state = "failed"
            if not self._logged_fail:
                self._logged_fail = True
                logger.error("[MediaPipe] FaceMesh init failed: %s", exc)
            return None

    def extract_metrics(self, img_bgr: np.ndarray) -> LandmarkMetrics:
        """
        img_bgr: uint8 HxWx3 BGR (OpenCV).
        """
        mesh = self._ensure_mesh()
        if mesh is None or img_bgr is None or img_bgr.size == 0:
            return LandmarkMetrics()

        h, w = img_bgr.shape[:2]
        if h <= 0 or w <= 0:
            return LandmarkMetrics()

        try:
            import cv2  # type: ignore
        except Exception as exc:
            logger.warning("[MediaPipe] OpenCV missing: %s", exc)
            return LandmarkMetrics()

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        result = mesh.process(img_rgb)
        if not result.multi_face_landmarks:
            return LandmarkMetrics()

        lm = result.multi_face_landmarks[0].landmark

        def pt(i: int) -> tuple[float, float]:
            return float(lm[i].x), float(lm[i].y)

        def dist(a: int, b: int) -> float:
            ax, ay = pt(a)
            bx, by = pt(b)
            return float(((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5)

        mouth_open = dist(13, 14)
        mouth_width = dist(61, 291)
        eye_open = (dist(159, 145) + dist(386, 374)) / 2.0

        _, brow_l_y = pt(105)
        _, eye_l_y = pt(159)
        _, brow_r_y = pt(334)
        _, eye_r_y = pt(386)
        brow_raise_l = max(0.0, eye_l_y - brow_l_y)
        brow_raise_r = max(0.0, eye_r_y - brow_r_y)
        brow_raise = (brow_raise_l + brow_raise_r) / 2.0
        brow_asym = abs(brow_raise_l - brow_raise_r)

        smile_signal = mouth_width - (mouth_open * 0.5)

        return LandmarkMetrics(
            mouth_open=mouth_open,
            mouth_width=mouth_width,
            eye_open=eye_open,
            brow_raise=brow_raise,
            brow_asym=brow_asym,
            smile_signal=smile_signal,
            face_present=True,
        )

    def heuristic_emotion(self, m: LandmarkMetrics) -> tuple[str, float]:
        """
        Lightweight classifier when DeepFace is unavailable or throttled.
        Thresholds match the legacy backend heuristics.
        """
        if not m.face_present:
            return "neutral", 0.5

        if m.smile_signal > 0.06 and m.mouth_width > 0.10:
            conf = min(0.95, 0.55 + (m.smile_signal - 0.06) * 5.0)
            return "happy", conf

        if m.brow_asym > 0.025 and m.brow_raise > 0.02:
            conf = min(0.9, 0.5 + (m.brow_asym - 0.025) * 10.0)
            return "confused", conf

        if m.brow_raise < 0.012 and m.eye_open < 0.018:
            conf = min(0.9, 0.5 + (0.018 - m.eye_open) * 20.0)
            return "frustrated", conf

        if m.eye_open >= 0.02 and m.mouth_open < 0.012:
            conf = min(0.9, 0.5 + (m.eye_open - 0.02) * 10.0)
            return "focused", conf

        return "neutral", 0.55

    def close(self) -> None:
        if self._mesh is not None:
            try:
                self._mesh.close()
            except Exception:
                logger.debug("[MediaPipe] close() ignored", exc_info=True)
            self._mesh = None
