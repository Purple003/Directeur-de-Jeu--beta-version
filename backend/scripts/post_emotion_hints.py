import json

import requests


URL = "http://127.0.0.1:8000/emotion/analyze"
EMOTIONS = ["happy", "neutral", "sad", "fear", "angry", "disgust", "surprise"]


def main() -> None:
    for i, emo in enumerate(EMOTIONS, start=1):
        # Use a different session_id per emotion to avoid server-side throttling/caching.
        payload = {"session_id": str(i), "emotion_hint": emo}
        try:
            r = requests.post(URL, json=payload, timeout=15)
        except Exception as exc:
            print(f"\n== {emo} ==")
            print("REQUEST ERROR:", exc)
            continue

        print(f"\n== {emo} ==")
        print("HTTP", r.status_code)
        try:
            print(json.dumps(r.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(r.text)


if __name__ == "__main__":
    main()
