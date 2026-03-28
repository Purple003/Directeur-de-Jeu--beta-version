using System;
using System.Collections;
using UnityEngine;

public class EmotionManager : MonoBehaviour
{
    [Header("Timing")]
    public float intervalSeconds = 60f;
    public bool storeToBackend = true;

    [Header("Debug (no camera)")]
    public bool enable = true;
    public bool useHealthHeuristic = true;
    public string fixedHint = "neutral";

    [Header("State (read-only)")]
    [SerializeField] private string lastState = "calm";
    [SerializeField] private float lastConfidence = 0f;

    public string LastState => lastState;
    public float LastConfidence => lastConfidence;

    public event Action<string, float> OnEmotionUpdated;

    private float lastSentAt = -999f;

    void Update()
    {
        if (!enable) return;
        if (APIManager.EnsureInstance() == null) return;

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null || st.sessionId <= 0) return;

        if (Time.unscaledTime - lastSentAt < Mathf.Max(5f, intervalSeconds)) return;
        lastSentAt = Time.unscaledTime;

        string hint = PickHint();
        StartCoroutine(SendHint(st.sessionId, hint));
    }

    string PickHint()
    {
        if (!useHealthHeuristic) return fixedHint;

        GameManager gm = FindObjectOfType<GameManager>();
        if (gm == null) return fixedHint;

        // Simple, deterministic heuristic for prototyping (no camera):
        // - Low HP => sad (stressed)
        // - Full HP => happy (engaged)
        // - Otherwise => neutral (calm)
        if (gm.CurrentHealth <= 1) return "sad";
        if (gm.CurrentHealth >= 3) return "happy";
        return "neutral";
    }

    IEnumerator SendHint(int sessionId, string hint)
    {
        bool ok = false;
        string state = lastState;
        float conf = lastConfidence;
        string err = "";

        yield return APIManager.Instance.PostEmotionHint(
            sessionId: sessionId,
            emotionHint: hint,
            store: storeToBackend,
            onOk: (s, c) => { ok = true; state = s; conf = c; },
            onErr: (e) => { ok = false; err = e; }
        );

        if (!ok)
        {
            Debug.LogWarning("[EmotionManager] /emotion/analyze failed: " + err);
            yield break;
        }

        lastState = state;
        lastConfidence = conf;
        OnEmotionUpdated?.Invoke(lastState, lastConfidence);
        Debug.Log($"[EmotionManager] state={lastState} conf={lastConfidence:0.00} (hint={hint})");
    }
}

