using UnityEngine;

public class PlayerSessionState : MonoBehaviour
{
    // NOTE: Some scenes can be loaded directly in the Editor (out of order).
    // We keep a stable, persistent state object via DontDestroyOnLoad + EnsureInstance().
    public static PlayerSessionState Instance;

    [Header("Player")]
    public int playerId = 1;
    public string playerName = "";

    [Header("Progress")]
    public int gameLevel = 1;
    public int xp = 0;
    public int stars = 0;

    [Header("Learning Session")]
    public int courseId = 1;
    public int sessionId = 0;

    [Header("Last Session Results")]
    public float lastFinalScore = 0f;
    public int lastDurationMs = 0;
    public int lastCorrect = 0;
    public int lastTotal = 0;
    public int lastXpGained = 0;
    public int lastStarsGained = 0;
    public int lastNextLevel = 1;
    public string lastRecommendedDifficulty = "";

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
        // Avoid stale static references (can happen during domain reload / scene unload in Editor).
        if (Instance == this) Instance = null;
    }

    /// <summary>
    /// Ensures PlayerSessionState exists even if scenes are loaded out of order.
    /// Safe to call from any scene at any time.
    /// </summary>
    public static PlayerSessionState EnsureInstance()
    {
        if (Instance != null) return Instance;

        // Try to find one placed in the scene first (keeps inspector-configured objects).
        PlayerSessionState existing = FindObjectOfType<PlayerSessionState>();
        if (existing != null)
        {
            Instance = existing;
            DontDestroyOnLoad(existing.gameObject);
            return Instance;
        }

        // Fallback: create one programmatically.
        GameObject go = new GameObject("PlayerSessionState");
        Instance = go.AddComponent<PlayerSessionState>();
        DontDestroyOnLoad(go);
        return Instance;
    }

    public bool HasValidPlayer() => playerId > 0;
    public bool HasValidCourse() => courseId > 0;
    public bool HasActiveSession() => sessionId > 0;

    /// <summary>
    /// Centralized validation for gameplay-related API calls.
    /// Keeps Unity-side errors consistent and avoids sending bad IDs to the backend.
    /// </summary>
    public bool ValidateIdsForGameplay(out string error)
    {
        if (playerId <= 0) { error = "playerId is missing (<= 0)."; return false; }
        if (courseId <= 0) { error = "courseId is missing (<= 0)."; return false; }
        error = "";
        return true;
    }

    public bool ValidateSessionIds(out string error)
    {
        if (!ValidateIdsForGameplay(out error)) return false;
        if (sessionId <= 0) { error = "sessionId is missing (<= 0)."; return false; }
        error = "";
        return true;
    }

    public void ResetSession()
    {
        sessionId = 0;
        lastFinalScore = 0f;
        lastDurationMs = 0;
        lastCorrect = 0;
        lastTotal = 0;
        lastXpGained = 0;
        lastStarsGained = 0;
        lastNextLevel = Mathf.Max(1, gameLevel);
        lastRecommendedDifficulty = "";
    }

    public void ApplyBackendProfile(APIManager.PlayerProfile p)
    {
        if (p == null) return;
        playerId = p.id;
        playerName = p.name;
        gameLevel = Mathf.Max(1, p.game_level > 0 ? p.game_level : 1);
        xp = Mathf.Max(0, p.xp);
        stars = Mathf.Max(0, p.stars);
    }
}
