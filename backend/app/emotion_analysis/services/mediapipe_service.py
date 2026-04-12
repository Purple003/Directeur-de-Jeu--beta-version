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

        # --- Implémentation FACS (Scale-invariant Ratios) ---
        face_width = dist(234, 454)  # Largeur totale du visage
        if face_width < 0.0001:
            face_width = 0.0001

        eye_width_l = dist(33, 133)
        eye_width_r = dist(362, 263)
        avg_eye_width = (eye_width_l + eye_width_r) / 2.0
        if avg_eye_width < 0.0001:
            avg_eye_width = 0.0001

        # Calcul de l'écart sourcils-yeux proportionnel au visage
        brow_eye_dist = (dist(107, 159) + dist(66, 386)) / 2.0
        
        facs_brow_down_ratio = brow_eye_dist / face_width
        facs_eye_opening_ratio = eye_open / avg_eye_width
        facs_mouth_width_ratio = mouth_width / face_width
        facs_mouth_open_ratio = mouth_open / face_width

        return LandmarkMetrics(
            mouth_open=mouth_open,
            mouth_width=mouth_width,
            eye_open=eye_open,
            brow_raise=brow_raise,
            brow_asym=brow_asym,
            smile_signal=smile_signal,
            face_present=True,
            facs_brow_down_ratio=facs_brow_down_ratio,
            facs_eye_opening_ratio=facs_eye_opening_ratio,
            facs_mouth_width_ratio=facs_mouth_width_ratio,
            facs_mouth_open_ratio=facs_mouth_open_ratio,
        )

    def heuristic_emotion(self, m: LandmarkMetrics) -> tuple[str, float]:
        """
        Système FACS en Ratios (Invariant à la distance caméra).
        """
        if not m.face_present:
            return "neutral", 0.5

        # Si face détectée MAIS yeux quasi-fermés = bored
        if m.face_present and m.facs_eye_opening_ratio < 0.12:
            return "bored", 0.80

        print(f"[DEBUG FACS] brow_ratio={m.facs_brow_down_ratio:.3f} | eye_ratio={m.facs_eye_opening_ratio:.3f} | mouth_w={m.facs_mouth_width_ratio:.3f} | mouth_o={m.facs_mouth_open_ratio:.3f}")

        # 1. Colère/Frustration : sourcils descendus vers les yeux
        # Valeurs normales de brow_ratio chez cet utilisateur : ~0.36-0.43
        # En fronçant fort, descend vers ~0.32-0.34
        if m.facs_brow_down_ratio < 0.34 and m.facs_eye_opening_ratio > 0.25:
            conf = min(0.95, 0.5 + (0.34 - m.facs_brow_down_ratio) * 10.0)
            return "frustrated", conf
        if m.facs_brow_down_ratio < 0.36:
            conf = min(0.78, 0.5 + (0.36 - m.facs_brow_down_ratio) * 7.0)
            return "frustrated", conf

        # 2. Joie/Happy : Étirement de la bouche par rapport à la largeur de la tête
        if m.facs_mouth_width_ratio > 0.40 and m.facs_mouth_open_ratio > 0.05:
            conf = min(0.9, 0.5 + (m.facs_mouth_width_ratio - 0.40) * 5.0)
            return "happy", conf

        # 3. Concentration/Focus : deux niveaux de tolérance
        # Niveau 1 : Yeux bien ouverts (fort engagement)
        if m.facs_eye_opening_ratio > 0.28 and m.facs_mouth_open_ratio < 0.10:
            conf = min(0.90, 0.5 + (m.facs_eye_opening_ratio - 0.28) * 4.0)
            return "focused", conf
        # Niveau 2 : Yeux légèrement mi-clos mais bouche fermée (concentration normale)
        if m.facs_eye_opening_ratio > 0.20 and m.facs_mouth_open_ratio < 0.08:
            conf = min(0.78, 0.5 + (m.facs_eye_opening_ratio - 0.20) * 3.5)
            return "focused", conf

        # 4. Ennui/Boredom : Yeux mi-clos / paupières tombantes, visage relâché
        if m.facs_eye_opening_ratio < 0.18 and m.facs_mouth_open_ratio < 0.15:
            conf = min(0.85, 0.5 + (0.18 - m.facs_eye_opening_ratio) * 4.0)
            return "bored", conf

        return "neutral", 0.55

    def close(self) -> None:
        if self._mesh is not None:
            try:
                self._mesh.close()
            except Exception:
                logger.debug("[MediaPipe] close() ignored", exc_info=True)
            self._mesh = None
