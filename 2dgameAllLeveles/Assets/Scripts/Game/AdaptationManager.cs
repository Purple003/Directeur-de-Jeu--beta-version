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

    void Awake()
    {
        if (emotion == null) emotion = FindObjectOfType<EmotionManager>();
    }

    public string CurrentState()
    {
        if (emotion == null) return "calm";
        string s = emotion.LastState;
        string v = string.IsNullOrWhiteSpace(s) ? "calm" : s.Trim().ToLower();

        // Normalize common backend/client labels to our 3-state adaptation model.
        if (v == "neutral" || v == "calm") return "calm";
        if (v == "happy" || v == "engaged") return "engaged";
        if (v == "sad" || v == "stressed") return "stressed";
        return "calm";
    }

    public float EnemySpeedMultiplier()
    {
        string s = CurrentState(); // calm -> normal (1x)
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
        // calm -> normal (no delay), engaged -> no delay, stressed -> add delay between spawns
        string s = CurrentState();
        if (s == "stressed") return Mathf.Max(0f, stressedSpawnDelaySeconds);
        return 0f;
    }
}
