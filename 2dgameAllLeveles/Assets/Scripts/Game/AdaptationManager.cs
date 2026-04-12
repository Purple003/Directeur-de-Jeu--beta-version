using UnityEngine;

public class AdaptationManager : MonoBehaviour
{
    [Header("References")]
    public EmotionManager emotion;

    [Header("Tuning")]
    public float stressedSpeedMultiplier = 0.8f;
    public float engagedSpeedMultiplier = 1.2f;
    public int stressedEnemyDelta = -2;
    public int engagedEnemyDelta = 2;
    public float stressedSpawnDelaySeconds = 0.35f;
    [Header("No-Fail Override")]
    [SerializeField] private float forcedStressedUntilUnscaled = -1f;

    public void ForceStressed(float seconds)
    {
        forcedStressedUntilUnscaled = Time.unscaledTime + Mathf.Max(0f, seconds);
    }

    bool IsForcedStressed()
    {
        return forcedStressedUntilUnscaled > 0f && Time.unscaledTime <= forcedStressedUntilUnscaled;
    }

    void Awake()
    {
        if (emotion == null) emotion = FindObjectOfType<EmotionManager>();
    }

    public string CurrentState()
            {
        if (IsForcedStressed()) return "stressed";
        if (emotion == null) return "bored";
        string s = emotion.LastState;
        string v = string.IsNullOrWhiteSpace(s) ? "bored" : s.Trim().ToLower();

        // Normalize common backend/client labels to our 3-state adaptation model.
        if (v == "bored" || v == "neutral") return "bored";
        if (v == "happy" || v == "engaged") return "engaged";
        if (v == "sad" || v == "stressed" || v == "frustrated") return "stressed";
        return "bored";
    }

    public float EnemySpeedMultiplier()
    {
        string s = CurrentState(); // bored -> normal (1x)
        if (s == "stressed") return Mathf.Max(0.1f, stressedSpeedMultiplier);
        if (s == "engaged") return Mathf.Max(0.1f, engagedSpeedMultiplier);
        return 1f;
    }

    public int AdjustEnemyCount(int baseCount)
    {
        int n = Mathf.Max(1, baseCount);
        string s = CurrentState();
        if (s == "stressed") n = Mathf.Max(1, n + stressedEnemyDelta);
        if (s == "engaged") n = Mathf.Max(1, n + engagedEnemyDelta);
        return n;
    }

    public float SpawnDelaySeconds()
    {
        // bored -> normal (no delay), engaged -> no delay, stressed -> add delay between spawns
        string s = CurrentState();
        if (s == "stressed") return Mathf.Max(0f, stressedSpawnDelaySeconds);
        return 0f;
    }
}
