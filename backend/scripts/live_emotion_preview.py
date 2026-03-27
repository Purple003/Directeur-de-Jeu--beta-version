"""
Live webcam preview using the fused pipeline (EmotionOrchestrator: MediaPipe + DeepFace + fusion).

Shows stress / engagement / boredom on the OpenCV window and updates one clean line in the console.
Does NOT call DeepFace directly — use this instead of test_deepface_live.py for fused metrics.

Press ESC in the OpenCV window to quit.

Run from `backend/`:
  set PYTHONPATH=.
  python scripts/live_emotion_preview.py
"""

from __future__ import annotations

import logging
import sys
import time
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import cv2

from app.emotion_analysis import EmotionOrchestrator

# Keep third-party noise down; fused metrics use print() below.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("live_preview")

FPS_WINDOW = 30


def _format_fused(out) -> str:
    """Single readable line: final fused state only (no raw DeepFace label)."""
    base = (
        f"Stress: {out.stress:.2f} | Engagement: {out.engagement:.2f} | Boredom: {out.boredom:.2f}"
    )
    return f"{base} | df_fresh={out.deepface_fresh}"


def main() -> int:
    orch = EmotionOrchestrator()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("Webcam 0 not available")
        return 1

    times: deque[float] = deque(maxlen=FPS_WINDOW)
    print("Fused metrics (updates in place). Press ESC in the video window to quit.\n")

    try:
        while True:
            t0 = time.perf_counter()
            ok, frame = cap.read()
            if not ok:
                break

            out = orch.analyze_bgr(frame)
            times.append(time.perf_counter() - t0)

            line = _format_fused(out)
            # One live line in the terminal (no scroll spam).
            print(f"\r{line}   ", end="", flush=True)

            # Overlay: same fused line only (readable on 720p+; wrap if needed)
            y = 28
            cv2.putText(
                frame,
                line,
                (8, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 180),
                2,
                cv2.LINE_AA,
            )
            if times:
                fps = len(times) / sum(times)
                cv2.putText(
                    frame,
                    f"loop ~{fps:.1f} FPS",
                    (8, y + 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 200, 255),
                    1,
                    cv2.LINE_AA,
                )

            cv2.imshow("Emotion fusion (stress / engagement / boredom)", frame)
            if cv2.waitKey(1) == 27:
                break
    finally:
        print()  # newline after \r line
        cap.release()
        cv2.destroyAllWindows()
        orch.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
