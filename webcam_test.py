"""Minimal OpenCV webcam check (default camera index 0)."""
import sys

import cv2


def main() -> int:
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open webcam at index 0.", file=sys.stderr)
        return 1

    ok, frame = cap.read()
    cap.release()

    if not ok or frame is None:
        print("ERROR: Failed to read a frame from the webcam.", file=sys.stderr)
        return 1

    h, w = frame.shape[:2]
    print(f"Webcam OK: captured frame {w}x{h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
