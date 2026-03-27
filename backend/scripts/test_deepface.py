import argparse
import logging
import sys


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("deepface-test")


def _fallback():
    logger.warning("[Emotion] Error \u2192 fallback")
    return {"emotion": "neutral", "confidence": 0.5}


def _load_frame_from_webcam(camera_index: int = 0):
    import cv2  # type: ignore

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open webcam index={camera_index}")
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read frame from webcam")
        return frame
    finally:
        cap.release()


def _load_frame_from_image(path: str):
    import cv2  # type: ignore

    frame = cv2.imread(path)
    if frame is None:
        raise RuntimeError(f"Unable to read image: {path}")
    return frame


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--image", help="Path to an image file (jpg/png)")
    p.add_argument("--webcam", action="store_true", help="Capture one frame from webcam")
    p.add_argument("--camera-index", type=int, default=0)
    args = p.parse_args()

    try:
        from deepface import DeepFace  # type: ignore

        logger.info("[Emotion] DeepFace loaded")
    except Exception as exc:
        logger.error("[Emotion] DeepFace not available: %s", exc)
        _fallback()
        return 2

    try:
        if args.webcam:
            frame = _load_frame_from_webcam(args.camera_index)
        elif args.image:
            frame = _load_frame_from_image(args.image)
        else:
            logger.error("Pass --webcam or --image <path>")
            return 2

        result = DeepFace.analyze(frame, actions=["emotion"], enforce_detection=False)
        if isinstance(result, list) and result:
            result = result[0]

        dominant = None
        conf = None
        if isinstance(result, dict):
            dominant = result.get("dominant_emotion")
            scores = result.get("emotion")
            if isinstance(scores, dict) and scores:
                best_label, best_val = None, None
                for k, v in scores.items():
                    try:
                        fv = float(v)
                    except Exception:
                        continue
                    if best_val is None or fv > best_val:
                        best_val = fv
                        best_label = str(k)
                if best_label is not None and best_val is not None:
                    dominant = best_label
                    conf = float(best_val) / 100.0

        emotion = (str(dominant) if dominant is not None else "neutral").strip().lower()
        if emotion == "surprise":
            emotion = "surprised"
        if emotion not in ("happy", "sad", "angry", "surprised", "neutral"):
            emotion = "neutral"

        confidence = float(conf) if conf is not None else 0.6
        confidence = max(0.0, min(1.0, confidence))

        logger.info("[Emotion] Detection success: %s (%.2f)", emotion, confidence)
        logger.info({"emotion": emotion, "confidence": confidence})
        return 0
    except Exception as exc:
        logger.error("[Emotion] DeepFace analyze failed: %s", exc)
        logger.info(_fallback())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

