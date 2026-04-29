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

        GameManager gmForSession = GameManager.Instance != null ? GameManager.Instance : FindObjectOfType<GameManager>();
        if (gmForSession == null || gmForSession.GetSessionId() <= 0) return;

        if (Time.unscaledTime - lastSentAt < Mathf.Max(5f, intervalSeconds)) return;
        lastSentAt = Time.unscaledTime;

        // --- Recherche de EmotionCamera ---
        EmotionCamera cam = FindObjectOfType<EmotionCamera>();

        // CASE 1 : La caméra existe et est active → on lui laisse la main, JAMAIS de fallback HTTP.
        if (cam != null && cam.enableCamera)
        {
            if (!string.IsNullOrEmpty(cam.LastEmotion))
            {
                // La caméra a déjà un résultat → on le lit passivement.
                lastState      = cam.LastEmotion;
                lastConfidence = cam.LastConfidence;
                OnEmotionUpdated?.Invoke(lastState, lastConfidence);
                Debug.Log($"[EmotionManager] Lecture depuis EmotionCamera : state={lastState} conf={lastConfidence:0.00}");
            }
            else
            {
                // La caméra est active mais n'a pas encore envoyé sa première frame → on attend.
                // AUCUNE requête HTTP ici, sinon le backend cache "neutral" et bloque la vraie photo.
                Debug.Log("[EmotionManager] EmotionCamera active mais LastEmotion encore vide → on attend sans envoyer de hint");
            }
            return;
        }

        // CASE 2 : Pas de caméra ou caméra désactivée → fallback hint uniquement.
        string hint = PickHint();
        Debug.Log("[EmotionManager] Pas de caméra active → fallback hint = '" + hint + "'");
        StartCoroutine(SendHint(hint));
    }

    string PickHint()
    {
        if (!useHealthHeuristic) return "neutral";

        GameManager gm = FindObjectOfType<GameManager>();
        if (gm == null) return "neutral";

        // Seul le stress critique (HP <= 1) est signalé. Jamais "happy".
        if (gm.CurrentHealth <= 1) return "sad";
        return "neutral";
    }

    IEnumerator SendHint(string hint)
    {
        bool ok = false;
        string state = lastState;
        float conf = lastConfidence;
        string err = "";

        yield return APIManager.Instance.PostEmotionHint(
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

        lastState      = state;
        lastConfidence = conf;
        OnEmotionUpdated?.Invoke(lastState, lastConfidence);
        Debug.Log($"[EmotionManager] state={lastState} conf={lastConfidence:0.00} (hint={hint})");
    }
}
