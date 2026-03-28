import base64
import json
from pathlib import Path

import requests


URL = "http://127.0.0.1:8000/emotion/analyze"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _find_test_images_dir() -> Path:
    cwd = Path.cwd() / "test_images"
    if cwd.is_dir():
        return cwd

    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / "test_images"
    if candidate.is_dir():
        return candidate

    return cwd


def _to_base64(path: Path) -> str:
    data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


def main() -> None:
    test_dir = _find_test_images_dir()
    if not test_dir.is_dir():
        raise SystemExit(f"Folder not found: {test_dir}")

    images = [p for p in sorted(test_dir.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    if not images:
        raise SystemExit(f"No images found in {test_dir} (expected: happy.jpg, sad.jpg, neutral.jpg, ...)")

    for img_path in images:
        emotion_hint = img_path.stem  # "happy" from "happy.jpg"
        payload = {
            "session_id": "1",
            "emotion_hint": emotion_hint,
            "image_base64": _to_base64(img_path),
        }

        print(f"\n== {img_path.name} ==")
        try:
            r = requests.post(URL, json=payload, timeout=30)
        except Exception as exc:
            print("REQUEST ERROR:", exc)
            continue

        print("HTTP", r.status_code)
        try:
            print(json.dumps(r.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(r.text)


if __name__ == "__main__":
    main()

