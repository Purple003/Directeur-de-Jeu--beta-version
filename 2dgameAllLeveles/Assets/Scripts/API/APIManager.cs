using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

public class APIManager : MonoBehaviour
{
    public static APIManager Instance;

    [Header("Backend")]
    public string baseURL = "http://127.0.0.1:8000";

    public string AccessToken { get; private set; } = "";

    [Header("Debug")]
    public bool debugLogging = true;

    // Prevent duplicate EndSession calls (can happen if gameplay ends while UI callbacks are still firing).
    private bool endSessionInFlight = false;
    private int endSessionInFlightId = 0;

    void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }
        else
        {
            Destroy(gameObject);
        }
    }

    void OnDestroy()
    {
        if (Instance == this) Instance = null;
    }

    /// <summary>
    /// Ensures APIManager exists even if scenes are loaded out of order.
    /// Safe to call from any scene at any time.
    /// </summary>
    public static APIManager EnsureInstance()
    {
        if (Instance != null) return Instance;

        // Prefer an inspector-configured instance if one exists in the currently loaded scene.
        APIManager existing = FindObjectOfType<APIManager>();
        if (existing != null)
        {
            Instance = existing;
            DontDestroyOnLoad(existing.gameObject);
            return Instance;
        }

        // Fallback: create a default APIManager programmatically.
        GameObject go = new GameObject("APIManager");
        Instance = go.AddComponent<APIManager>();
        DontDestroyOnLoad(go);
        return Instance;
    }

    void SetAuth(UnityWebRequest req)
    {
        if (!string.IsNullOrEmpty(AccessToken))
        {
            req.SetRequestHeader("Authorization", "Bearer " + AccessToken);
        }
    }

    string ExtractErrorMessage(string body)
    {
        if (string.IsNullOrEmpty(body)) return "Empty response body.";
        try
        {
            ApiEnvelopeAny env = JsonUtility.FromJson<ApiEnvelopeAny>(body);
            if (env != null && env.error != null && !string.IsNullOrEmpty(env.error.message))
            {
                return env.error.message;
            }
        }
        catch { }
        // Backend might return { "detail": ... } for non-enveloped responses (e.g. dashboard/redirect).
        return body.Length > 600 ? body.Substring(0, 600) + "..." : body;
    }

    public IEnumerator Login(string username, string password, Action<bool, string> callback)
    {
        string url = baseURL + "/auth/login";
        LoginRequest data = new LoginRequest { username = username, password = password };
        string json = JsonUtility.ToJson(data);

        using (UnityWebRequest request = new UnityWebRequest(url, "POST"))
        {
            request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            SetAuth(request);
            yield return request.SendWebRequest();

            if (request.result == UnityWebRequest.Result.Success)
            {
                ApiEnvelopeLogin env = JsonUtility.FromJson<ApiEnvelopeLogin>(request.downloadHandler.text);
                if (env != null && env.success && env.data != null)
                {
                    AccessToken = env.data.access_token;
                    callback?.Invoke(true, "");
                }
                else
                {
                    callback?.Invoke(false, (env != null && env.error != null) ? env.error.message : "Login failed.");
                }
            }
            else
            {
                callback?.Invoke(false, $"{request.responseCode} {request.downloadHandler.text}");
            }
        }
    }

    public IEnumerator CreatePlayer(string name, int? age, string schoolLevel, string experienceLevel, Action<int> onOk, Action<string> onErr)
    {
        string url = baseURL + "/player/create";
        // Build JSON manually so we can omit optional fields (JsonUtility doesn't omit default values well).
        string json = "{\"name\":\"" + Escape(name) + "\"";
        if (age.HasValue && age.Value >= 3) json += ",\"age\":" + age.Value;
        if (!string.IsNullOrEmpty(schoolLevel)) json += ",\"school_level\":\"" + Escape(schoolLevel) + "\"";
        if (!string.IsNullOrEmpty(experienceLevel)) json += ",\"experience_level\":\"" + Escape(experienceLevel) + "\"";
        json += "}";

        using (UnityWebRequest req = new UnityWebRequest(url, "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            SetAuth(req);
            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                ApiEnvelopePlayerCreate env = JsonUtility.FromJson<ApiEnvelopePlayerCreate>(req.downloadHandler.text);
                if (env != null && env.success && env.data != null)
                {
                    onOk?.Invoke(env.data.player_id);
                }
                else
                {
                    onErr?.Invoke((env != null && env.error != null) ? env.error.message : "Create player failed.");
                }
            }
            else
            {
                onErr?.Invoke($"{req.responseCode} {req.downloadHandler.text}");
            }
        }
    }

    public IEnumerator GetPlayer(int playerId, Action<PlayerProfile> onOk, Action<string> onErr)
    {
        string url = baseURL + "/player/" + playerId;
        using (UnityWebRequest req = UnityWebRequest.Get(url))
        {
            SetAuth(req);
            yield return req.SendWebRequest();
            if (req.result == UnityWebRequest.Result.Success)
            {
                ApiEnvelopePlayerProfile env = JsonUtility.FromJson<ApiEnvelopePlayerProfile>(req.downloadHandler.text);
                if (env != null && env.success && env.data != null)
                {
                    onOk?.Invoke(env.data);
                }
                else
                {
                    onErr?.Invoke((env != null && env.error != null) ? env.error.message : "Player not found.");
                }
            }
            else
            {
                onErr?.Invoke($"{req.responseCode} {req.downloadHandler.text}");
            }
        }
    }

    public IEnumerator StartSession(int playerId, int courseId, Action<int> onOk, Action<string> onErr)
    {
        string url = baseURL + "/game/start-session";
        StartSessionRequest payload = new StartSessionRequest { player_id = playerId, course_id = courseId };
        string json = JsonUtility.ToJson(payload);

        using (UnityWebRequest req = new UnityWebRequest(url, "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            SetAuth(req);
            if (debugLogging) Debug.Log($"[API] StartSession playerId={playerId} courseId={courseId} url={url} payload={json}");
            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                ApiEnvelopeStartSession env = JsonUtility.FromJson<ApiEnvelopeStartSession>(req.downloadHandler.text);
                if (env != null && env.success && env.data != null)
                {
                    onOk?.Invoke(env.data.session_id);
                }
                else
                {
                    onErr?.Invoke((env != null && env.error != null) ? env.error.message : "Start session failed.");
                }
            }
            else
            {
                onErr?.Invoke($"HTTP {req.responseCode}: {ExtractErrorMessage(req.downloadHandler.text)}");
            }
        }
    }

    public IEnumerator GetQuestions(int courseId, int playerId, Action<GameQuestion[]> onOk, Action<string> onErr)
    {
        string url = $"{baseURL}/game/questions/{courseId}?player_id={playerId}&limit=20";
        using (UnityWebRequest req = UnityWebRequest.Get(url))
        {
            SetAuth(req);
            if (debugLogging) Debug.Log($"[API] GetQuestions courseId={courseId} playerId={playerId} url={url}");
            yield return req.SendWebRequest();
            if (req.result == UnityWebRequest.Result.Success)
            {
                string raw = req.downloadHandler != null ? (req.downloadHandler.text ?? "") : "";
                if (debugLogging)
                {
                    string preview = raw.Length > 2000 ? raw.Substring(0, 2000) + "..." : raw;
                    Debug.Log($"[API] GetQuestions rawJson={preview}");
                }

                // Backend returns: { "success": true, "data": { "course_id": int, "questions": [...] }, "error": null }
                QuestionsResponseWrapper env = null;
                try { env = JsonUtility.FromJson<QuestionsResponseWrapper>(raw); } catch { env = null; }

                if (env != null && env.success && env.data != null)
                {
                    Question[] parsed = env.data.questions;
                    int parsedCount = (parsed != null) ? parsed.Length : 0;
                    if (debugLogging) Debug.Log($"[API] GetQuestions parsedCount={parsedCount} courseId={env.data.course_id}");

                    if (parsed == null || parsed.Length == 0)
                    {
                        Debug.LogError($"[API] GetQuestions: questions list is null/empty for courseId={courseId}. Check backend data/questions.");
                        onOk?.Invoke(new GameQuestion[0]);
                        yield break;
                    }

                    // Map to the existing GameQuestion model used by gameplay scripts.
                    GameQuestion[] mapped = new GameQuestion[parsed.Length];
                    for (int i = 0; i < parsed.Length; i++)
                    {
                        Question q = parsed[i];
                        mapped[i] = new GameQuestion
                        {
                            id = q.id,
                            course_id = q.course_id,
                            question = q.question,
                            choices = q.choices,
                            correct_answer = q.correct_answer,
                            difficulty_level = q.difficulty_level,
                        };
                    }
                    onOk?.Invoke(mapped);
                }
                else
                {
                    string msg = (env != null && env.error != null && !string.IsNullOrEmpty(env.error.message))
                        ? env.error.message
                        : "Failed to parse /game/questions response (expected data.questions).";
                    onErr?.Invoke(msg);
                }
            }
            else
            {
                onErr?.Invoke($"HTTP {req.responseCode}: {ExtractErrorMessage(req.downloadHandler.text)}");
            }
        }
    }

    /// <summary>
    /// Server-controlled adaptive selection of the next question for a session.
    /// IMPORTANT: Unity must not pick questions randomly.
    /// </summary>
    public IEnumerator GetNextQuestion(int sessionId, Action<GameQuestion> onOk, Action<string> onErr)
    {
        if (sessionId <= 0)
        {
            onErr?.Invoke("GetNextQuestion blocked: session_id is missing (<= 0).");
            yield break;
        }

        string url = $"{baseURL}/game/sessions/{sessionId}/next-question";
        using (UnityWebRequest req = UnityWebRequest.Get(url))
        {
            SetAuth(req);
            if (debugLogging) Debug.Log($"[API] GetNextQuestion sessionId={sessionId} url={url}");
            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                ApiEnvelopeNextQuestion env = null;
                try { env = JsonUtility.FromJson<ApiEnvelopeNextQuestion>(req.downloadHandler.text); }
                catch { env = null; }

                if (env != null && env.success && env.data != null)
                {
                    // Update session state with the backend decision (difficulty/level).
                    PlayerSessionState st = PlayerSessionState.EnsureInstance();
                    if (st != null)
                    {
                        st.gameLevel = Mathf.Max(1, env.data.player_level);
                        st.lastRecommendedDifficulty = env.data.recommended_difficulty ?? "";
                    }

                    if (env.data.question != null && env.data.question.id > 0)
                    {
                        onOk?.Invoke(env.data.question);
                    }
                    else
                    {
                        onErr?.Invoke("No more questions available for this session.");
                    }
                }
                else
                {
                    onErr?.Invoke((env != null && env.error != null) ? env.error.message : "GetNextQuestion failed.");
                }
            }
            else
            {
                string body = req.downloadHandler != null ? req.downloadHandler.text : "";
                onErr?.Invoke($"HTTP {req.responseCode}: {ExtractErrorMessage(body)}");
            }
        }
    }

    public IEnumerator SubmitAnswer(SubmitAnswerRequest payload, Action<bool> onOk, Action<string> onErr)
    {
        string url = baseURL + "/game/submit-answer";
        if (payload == null)
        {
            onErr?.Invoke("SubmitAnswer payload is null.");
            yield break;
        }
        if (payload.session_id <= 0)
        {
            onErr?.Invoke("SubmitAnswer blocked: session_id is missing (session not initialized).");
            yield break;
        }
        if (payload.question_id <= 0)
        {
            onErr?.Invoke("SubmitAnswer blocked: question_id is missing.");
            yield break;
        }
        if (string.IsNullOrEmpty(payload.selected_answer))
        {
            onErr?.Invoke("SubmitAnswer blocked: selected_answer is empty.");
            yield break;
        }

        string json = JsonUtility.ToJson(payload);
        if (debugLogging) Debug.Log($"[API] SubmitAnswer url={url} payload={json}");

        using (UnityWebRequest req = new UnityWebRequest(url, "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            SetAuth(req);
            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                ApiEnvelopeSubmitAnswer env = JsonUtility.FromJson<ApiEnvelopeSubmitAnswer>(req.downloadHandler.text);
                if (env != null && env.success && env.data != null)
                {
                    onOk?.Invoke(env.data.is_correct);
                }
                else
                {
                    onErr?.Invoke((env != null && env.error != null) ? env.error.message : "Submit failed.");
                }
            }
            else
            {
                string body = req.downloadHandler != null ? req.downloadHandler.text : "";
                onErr?.Invoke($"HTTP {req.responseCode}: {ExtractErrorMessage(body)}");
            }
        }
    }

    /// <summary>
    /// Centralized SubmitAnswer helper used by UI/gameplay code.
    /// Prevents sending invalid session_id/question_id to the backend and keeps logs consistent.
    /// </summary>
    public IEnumerator SubmitAnswerForCurrentSession(
        int questionId,
        string selectedAnswer,
        int timeSpentMs,
        string emotion,
        float confidence,
        Action<bool> onOk,
        Action<string> onErr
    )
    {
        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null)
        {
            onErr?.Invoke("SubmitAnswer blocked: PlayerSessionState missing.");
            yield break;
        }

        if (!st.ValidateSessionIds(out string idErr))
        {
            onErr?.Invoke("SubmitAnswer blocked: " + idErr);
            yield break;
        }

        if (questionId <= 0)
        {
            onErr?.Invoke("SubmitAnswer blocked: questionId is missing (<= 0).");
            yield break;
        }

        if (string.IsNullOrWhiteSpace(selectedAnswer))
        {
            onErr?.Invoke("SubmitAnswer blocked: selectedAnswer is empty.");
            yield break;
        }

        SubmitAnswerRequest payload = new SubmitAnswerRequest
        {
            session_id = st.sessionId,
            question_id = questionId,
            selected_answer = selectedAnswer.Trim(),
            time_spent_ms = Mathf.Max(0, timeSpentMs),
            emotion = string.IsNullOrWhiteSpace(emotion) ? null : emotion.Trim(),
            confidence = Mathf.Clamp01(confidence),
        };

        if (debugLogging)
        {
            Debug.Log(
                $"[API] SubmitAnswer(sessionId={payload.session_id}, questionId={payload.question_id}, selected={payload.selected_answer}, timeMs={payload.time_spent_ms}, emotion={payload.emotion}, conf={payload.confidence:0.00})"
            );
        }

        yield return SubmitAnswer(payload, onOk, onErr);
    }

    public IEnumerator EndSession(int sessionId, Action<EndSessionData> onOk, Action<string> onErr)
    {
        string url = baseURL + "/game/end-session";
        // Backend computes final_score automatically.
        if (sessionId <= 0)
        {
            onErr?.Invoke("EndSession blocked: session_id is missing (session not initialized).");
            yield break;
        }

        // Idempotency guard: if the same EndSession is already in flight, block the duplicate call.
        if (endSessionInFlight && endSessionInFlightId == sessionId)
        {
            onErr?.Invoke("EndSession blocked: already in progress for this session.");
            yield break;
        }

        endSessionInFlight = true;
        endSessionInFlightId = sessionId;
        string json = "{\"session_id\":" + sessionId + "}";
        if (debugLogging) Debug.Log($"[API] EndSession url={url} payload={json}");

        using (UnityWebRequest req = new UnityWebRequest(url, "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            SetAuth(req);
            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                ApiEnvelopeEndSession env = JsonUtility.FromJson<ApiEnvelopeEndSession>(req.downloadHandler.text);
                if (env != null && env.success && env.data != null)
                {
                    onOk?.Invoke(env.data);
                }
                else
                {
                    onErr?.Invoke((env != null && env.error != null) ? env.error.message : "End session failed.");
                }
            }
            else
            {
                string body = req.downloadHandler != null ? req.downloadHandler.text : "";
                onErr?.Invoke($"HTTP {req.responseCode}: {ExtractErrorMessage(body)}");
            }
        }

        // Always clear in-flight flags, even on failure.
        endSessionInFlight = false;
        endSessionInFlightId = 0;
    }

    public IEnumerator UpdateProgress(int playerId, int xpDelta, int starsDelta, Action<UpdateProgressData> onOk, Action<string> onErr)
    {
        string url = baseURL + "/game/update-progress";
        string json = "{\"player_id\":" + playerId + ",\"xp_delta\":" + xpDelta + ",\"stars_delta\":" + starsDelta + "}";

        using (UnityWebRequest req = new UnityWebRequest(url, "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            SetAuth(req);
            if (debugLogging) Debug.Log($"[API] UpdateProgress url={url} payload={json}");
            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                ApiEnvelopeUpdateProgress env = JsonUtility.FromJson<ApiEnvelopeUpdateProgress>(req.downloadHandler.text);
                if (env != null && env.success && env.data != null)
                {
                    onOk?.Invoke(env.data);
                }
                else
                {
                    onErr?.Invoke((env != null && env.error != null) ? env.error.message : "Update progress failed.");
                }
            }
            else
            {
                string body = req.downloadHandler != null ? req.downloadHandler.text : "";
                onErr?.Invoke($"HTTP {req.responseCode}: {ExtractErrorMessage(body)}");
            }
        }
    }

    // ---------- API Models (JsonUtility-friendly) ----------

    [Serializable] public class ApiError { public string message; public string details; }
    [Serializable] public class ApiEnvelopeAny { public bool success; public ApiError error; }

    [Serializable] public class LoginRequest { public string username; public string password; }
    [Serializable] public class LoginData { public string access_token; public string token_type; public string role; }
    [Serializable] public class ApiEnvelopeLogin { public bool success; public LoginData data; public ApiError error; }

    [Serializable] public class PlayerCreateData { public string message; public int player_id; }
    [Serializable] public class ApiEnvelopePlayerCreate { public bool success; public PlayerCreateData data; public ApiError error; }

    [Serializable] public class PlayerProfile
    {
        public int id;
        public string name;
        public int age;
        public string school_level;
        public string experience_level;
        public int game_level;
        public int xp;
        public int stars;
    }
    [Serializable] public class ApiEnvelopePlayerProfile { public bool success; public PlayerProfile data; public ApiError error; }

    [Serializable] public class StartSessionRequest { public int player_id; public int course_id; }
    [Serializable] public class StartSessionData { public string message; public int session_id; }
    [Serializable] public class ApiEnvelopeStartSession { public bool success; public StartSessionData data; public ApiError error; }

    [Serializable] public class GameQuestionsData { public int course_id; public GameQuestion[] questions; }
    [Serializable] public class ApiEnvelopeGameQuestions { public bool success; public GameQuestionsData data; public ApiError error; }

    // ---------- /game/questions wrapper (Unity JsonUtility-safe) ----------
    // JsonUtility sometimes fails silently if the shape doesn't match exactly; keep a dedicated wrapper
    // that mirrors the backend response: { success, data: { course_id, questions: [...] }, error }.
    [Serializable] public class QuestionsResponseWrapper { public bool success; public QuestionsData data; public ApiError error; }
    [Serializable] public class QuestionsData { public int course_id; public Question[] questions; }
    [Serializable] public class Question
    {
        public int id;
        public int course_id;
        public string question;
        public string[] choices;
        public string correct_answer;
        public string difficulty_level;
    }

    [Serializable] public class GameQuestion
    {
        public int id;
        public int course_id;
        public string question;
        public string[] choices;
        public string correct_answer;
        public string difficulty_level;
    }

    [Serializable] public class NextQuestionData
    {
        public int session_id;
        public int course_id;
        public int player_level;
        public string recommended_difficulty;
        public GameQuestion question;
        public int remaining_in_difficulty;
        public int remaining_total;
    }
    [Serializable] public class ApiEnvelopeNextQuestion { public bool success; public NextQuestionData data; public ApiError error; }

    [Serializable] public class SubmitAnswerRequest
    {
        public int session_id;
        public int question_id;
        public string selected_answer;
        public int time_spent_ms;
        public string emotion;
        public float confidence;
    }
    [Serializable] public class SubmitAnswerData { public string message; public bool is_correct; }
    [Serializable] public class ApiEnvelopeSubmitAnswer { public bool success; public SubmitAnswerData data; public ApiError error; }

    [Serializable] public class EndSessionData
    {
        public string message;
        public int session_id;
        public float final_score;
        public int duration_ms;
        public int next_level;
        public string recommended_difficulty;
    }
    [Serializable] public class ApiEnvelopeEndSession { public bool success; public EndSessionData data; public ApiError error; }

    [Serializable] public class UpdateProgressData
    {
        public string message;
        public int player_id;
        public int xp;
        public int stars;
        public int game_level;
    }

    [Serializable] public class ApiEnvelopeUpdateProgress { public bool success; public UpdateProgressData data; public ApiError error; }

    static string Escape(string s)
    {
        if (s == null) return "";
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
