# backend/test_mediapipe_live.py

import cv2
import mediapipe as mp

mp_face = mp.solutions.face_mesh
cap = cv2.VideoCapture(0)

with mp_face.FaceMesh() as face_mesh:
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        if results.multi_face_landmarks:
            print("FACE DETECTED")
        else:
            print("NO FACE")

        cv2.imshow("MediaPipe", frame)

        if cv2.waitKey(1) == 27:
            break

cap.release()
cv2.destroyAllWindows()