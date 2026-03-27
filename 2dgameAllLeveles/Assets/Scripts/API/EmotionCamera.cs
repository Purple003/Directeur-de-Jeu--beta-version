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
    public float sendIntervalSeconds = 3f;
    public bool logFailures = false;

    [NonSerialized] public string lastEmotion = "";
    [NonSerialized] public float lastConfidence = 0f;

    private WebCamTexture cam;
    private Texture2D snap;
    private int questionIdContext = 0;
    private float lastSentAt = -999f;

    [Serializable] class ApiError { public string message; public string details; }
    [Serializable] class EmotionData { public string emotion; public float confidence; }
    [Serializable] class ApiEnvelopeEmotion { public bool success; public EmotionData data; public ApiError error; }

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
        if (APIManager.EnsureInstance() == null) return;
        if (cam == null || !cam.isPlaying) return;
        if (!cam.didUpdateThisFrame) return;
        if (Time.unscaledTime - lastSentAt < sendIntervalSeconds) return;

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null || st.sessionId <= 0) return;

        lastSentAt = Time.unscaledTime;
        StartCoroutine(SendFrame(st.sessionId, questionIdContext));
    }

    IEnumerator SendFrame(int sessionId, int questionId)
    {
        // Grab pixels from camera
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
            if (req.result != UnityWebRequest.Result.Success)
            {
                if (logFailures) Debug.LogWarning("[API] Emotion analyze failed: " + req.responseCode + " " + req.downloadHandler.text);
                yield break;
            }

            ApiEnvelopeEmotion env = null;
            try { env = JsonUtility.FromJson<ApiEnvelopeEmotion>(req.downloadHandler.text); }
            catch { }

            if (env != null && env.success && env.data != null)
            {
                lastEmotion = env.data.emotion ?? "";
                lastConfidence = env.data.confidence;
            }
            else
            {
                if (logFailures)
                {
                    string msg = (env != null && env.error != null) ? env.error.message : "unknown";
                    Debug.LogWarning("[API] Emotion analyze error: " + msg);
                }
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
}
