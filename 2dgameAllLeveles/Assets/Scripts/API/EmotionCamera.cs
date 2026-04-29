using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

// Captures webcam frames and periodically calls POST /emotion/analyze (multipart form-data).
// Keeps the last detected emotion so QuizUIManager can attach it to /game/submit-answer.
public class EmotionCamera : MonoBehaviour
{
    [Header("Capture")]
    public bool enableCamera = true;
    public int targetWidth = 320;
    public int targetHeight = 240;
    [Range(10, 95)] public int jpgQuality = 60;

    [Header("Send")]
    // Backend enforces throttling too, but keep the client lightweight: send at most once per minute.
    public float sendIntervalSeconds = 60f;
    public bool logFailures = false;

    [NonSerialized] public string lastEmotion = "";
    [NonSerialized] public float lastConfidence = 0f;

    // Public read-only accessors for EmotionManager (PascalCase convention).
    public string LastEmotion => lastEmotion;
    public float LastConfidence => lastConfidence;

    private WebCamTexture cam;
    private Texture2D snap;
    private int questionIdContext = 0;
    private float lastSentAt = -999f;

    [Serializable] class EmotionState { public string state; public float confidence; }

    void Start()
    {
        if (!enableCamera) return;

        try
        {
            cam = new WebCamTexture(targetWidth, targetHeight);
            cam.Play();
            snap = new Texture2D(targetWidth, targetHeight, TextureFormat.RGB24, false);
        }
        catch (Exception e)
        {
            Debug.LogWarning("[API] EmotionCamera init failed: " + e.Message);
            enableCamera = false;
        }
    }

    public void SetQuestionContext(int questionId)
    {
        questionIdContext = Mathf.Max(0, questionId);
    }

    void Update()
    {
        if (!enableCamera) return;
        if (APIManager.EnsureInstance() == null)
        {
            Debug.Log("[EmotionCamera] BLOCKED: APIManager.Instance is null");
            return;
        }
        if (cam == null || !cam.isPlaying)
        {
            Debug.Log("[EmotionCamera] BLOCKED: webcam unavailable (cam=" + (cam != null) + " isPlaying=" + (cam != null ? cam.isPlaying.ToString() : "N/A") + ")");
            return;
        }
        if (!cam.didUpdateThisFrame) return;

        float elapsed = Time.unscaledTime - lastSentAt;
        if (elapsed < sendIntervalSeconds) return;

        GameManager gameManager = GameManager.Instance != null ? GameManager.Instance : FindObjectOfType<GameManager>();
        int sessionId = gameManager != null ? gameManager.GetSessionId() : 0;
        int courseId = gameManager != null ? gameManager.CourseId : 0;
        if (sessionId <= 0)
        {
            int gmId = gameManager != null ? gameManager.GetInstanceID() : 0;
            Debug.Log("[EmotionCamera] BLOCKED: sessionId == 0. gameManagerInstanceId=" + gmId);
            return;
        }

        Debug.Log("[SYNC] Using sessionId=" + sessionId + " courseId=" + courseId);
        Debug.Log("[EmotionCamera] Tentative d'envoi de frame, sessionId=" + sessionId + " questionId=" + questionIdContext);
        lastSentAt = Time.unscaledTime;
        StartCoroutine(SendFrame(sessionId, questionIdContext));
    }

    IEnumerator SendFrame(int sessionId, int questionId)
    {
        try
        {
            Color32[] pixels = cam.GetPixels32();
            if (pixels == null || pixels.Length == 0) yield break;
            snap.SetPixels32(pixels);
            snap.Apply(false);
        }
        catch
        {
            yield break;
        }

        byte[] jpg = null;
        try { jpg = snap.EncodeToJPG(jpgQuality); }
        catch { yield break; }
        if (jpg == null || jpg.Length == 0) yield break;

        string url = APIManager.Instance.baseURL + "/emotion/analyze";
        WWWForm form = new WWWForm();
        form.AddField("session_id", sessionId.ToString());
        if (questionId > 0) form.AddField("question_id", questionId.ToString());
        form.AddBinaryData("frame", jpg, "frame.jpg", "image/jpeg");

        using (UnityWebRequest req = UnityWebRequest.Post(url, form))
        {
            yield return req.SendWebRequest();

            Debug.Log("[EmotionCamera] HTTP response code: " + req.responseCode);

            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.Log("[EmotionCamera] NETWORK ERROR: " + req.error);
                if (logFailures) Debug.LogWarning("[API] Emotion analyze failed: " + req.responseCode + " " + req.downloadHandler.text);
                yield break;
            }

            Debug.Log("[EmotionCamera] Response text: " + req.downloadHandler.text);

            EmotionState outp = null;
            try { outp = JsonUtility.FromJson<EmotionState>(req.downloadHandler.text); }
            catch { }

            if (outp != null)
            {
                lastEmotion = outp.state ?? "";
                lastConfidence = outp.confidence;
            }
            else if (logFailures)
            {
                Debug.LogWarning("[API] Emotion analyze parse error: " + req.downloadHandler.text);
            }
        }
    }

    void OnDestroy()
    {
        if (cam != null)
        {
            try { cam.Stop(); } catch { }
        }
    }

    public void AnalyzeNow(int questionId)
    {
        if (!enableCamera) return;
        if (APIManager.EnsureInstance() == null) return;

        GameManager gameManager = GameManager.Instance != null ? GameManager.Instance : FindObjectOfType<GameManager>();
        int sessionId = gameManager != null ? gameManager.GetSessionId() : 0;
        int courseId = gameManager != null ? gameManager.CourseId : 0;
        if (sessionId <= 0)
        {
            int gmId = gameManager != null ? gameManager.GetInstanceID() : 0;
            Debug.LogError("[EmotionCamera] AnalyzeNow blocked: sessionId == 0. gameManagerInstanceId=" + gmId);
            return;
        }

        Debug.Log("[SYNC] Using sessionId=" + sessionId + " courseId=" + courseId);

        if (cam == null || snap == null || !cam.isPlaying)
        {
            try
            {
                if (cam == null) cam = new WebCamTexture(targetWidth, targetHeight);
                if (!cam.isPlaying) cam.Play();
                if (snap == null) snap = new Texture2D(targetWidth, targetHeight, TextureFormat.RGB24, false);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[API] EmotionCamera init failed: " + e.Message);
                enableCamera = false;
                return;
            }
        }

        questionIdContext = Mathf.Max(0, questionId);
        lastSentAt = Time.unscaledTime;
        StartCoroutine(SendFrame(sessionId, questionIdContext));
    }
}
