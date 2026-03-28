from __future__ import annotations

import logging
import os
import time
import concurrent.futures

import numpy as np

from ..models.signals import DeepFaceSnapshot

logger = logging.getLogger(__name__)

# DeepFace percentage scores → normalized names
_SCORE_KEYS = ("angry", "disgust", "fear", "happy", "sad", "surprise", "neutral")


class DeepFaceEmotionRunner:
    """
    Runs DeepFace in a dedicated worker thread so FastAPI / capture loops stay responsive.

    At most one analysis in flight; if busy, returns a throttled snapshot (caller may use cache).
    """

    def __init__(
        self,
        *,
        min_interval_s: float | None = None,
    ) -> None:
        self._min_interval_s = float(
            min_interval_s if min_interval_s is not None else os.getenv("EMOTION_MIN_INTERVAL_S", "1.5") or "1.5"
        )
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._in_flight = None
        self._df = None
        self._state: str = "unknown"
        self._last_at: float = 0.0
        self._cache: DeepFaceSnapshot | None = None
        self._logged_missing = False

    def _get_deepface(self):
        if self._state in ("missing", "failed"):
            return None
        if self._df is not None:
            return self._df
        try:
            from deepface import DeepFace  # type: ignore
        except Exception as exc:
            self._state = "missing"
            if not self._logged_missing:
                self._logged_missing = True
                logger.error("[DeepFace] import failed: %s", exc)
            return None
        self._df = DeepFace
        self._state = "ok"
        logger.info("[DeepFace] loaded")
        return self._df

    def _parse_result(self, raw: object) -> DeepFaceSnapshot | None:
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if not isinstance(raw, dict):
            return None

        emo = raw.get("dominant_emotion") or raw.get("dominant_emotion".encode("utf-8"))
        scores_raw = raw.get("emotion")
        scores: dict[str, float] = {}
        if isinstance(scores_raw, dict) and scores_raw:
            for k, v in scores_raw.items():
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                key = str(k).lower()
                scores[key] = fv / 100.0 if fv > 1.0 else fv
            for k in _SCORE_KEYS:
                scores.setdefault(k, 0.0)
        dom = str(emo).lower() if emo else None
        if not dom:
            if scores:
                dom = max(scores, key=scores.get)
            else:
                return None
        conf = float(scores.get(dom, 0.6)) if scores else 0.6
        conf = max(0.0, min(1.0, conf))
        return DeepFaceSnapshot(dominant=dom, confidence=conf, scores=scores, is_fresh=True)

    def analyze(self, img_bgr: np.ndarray) -> DeepFaceSnapshot | None:
        """
        Non-blocking DeepFace integration:
        - Schedules DeepFace work in a background thread.
        - Returns the latest cached snapshot (is_fresh=False) immediately.

        This keeps FastAPI endpoints responsive even when DeepFace is slow.
        """
        df = self._get_deepface()
        if df is None:
            return None

        now = time.monotonic()

        # Throttle: do not schedule new work too often.
        if self._cache is not None and self._min_interval_s > 0 and (now - self._last_at) < self._min_interval_s:
            return DeepFaceSnapshot(
                dominant=self._cache.dominant,
                confidence=self._cache.confidence,
                scores=dict(self._cache.scores),
                is_fresh=False,
                error="throttled",
            )

        # Drop completed handle (cache update happens in callback).
        if self._in_flight is not None and self._in_flight.done():
            self._in_flight = None

        # If a job is running, return cache immediately.
        if self._in_flight is not None and not self._in_flight.done():
            if self._cache is not None:
                return DeepFaceSnapshot(
                    dominant=self._cache.dominant,
                    confidence=self._cache.confidence,
                    scores=dict(self._cache.scores),
                    is_fresh=False,
                    error="busy",
                )
            return None

        # Schedule new work and return cache immediately.
        def _run():
            return df.analyze(img_bgr, actions=["emotion"], enforce_detection=False)

        fut = self._executor.submit(_run)
        self._in_flight = fut
        fut.add_done_callback(self._on_done)

        if self._cache is not None:
            return DeepFaceSnapshot(
                dominant=self._cache.dominant,
                confidence=self._cache.confidence,
                scores=dict(self._cache.scores),
                is_fresh=False,
                error="scheduled",
            )
        return None

    def _on_done(self, fut: concurrent.futures.Future) -> None:
        try:
            raw = fut.result(timeout=0)
        except Exception as exc:
            logger.debug("[DeepFace] background job failed: %s", exc)
            return

        try:
            snap = self._parse_result(raw)
        except Exception as exc:
            logger.debug("[DeepFace] background parse failed: %s", exc)
            return

        if snap is None:
            return
        self._cache = snap
        self._last_at = time.monotonic()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
