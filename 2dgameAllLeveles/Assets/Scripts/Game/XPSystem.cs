using UnityEngine;

public class XPSystem : MonoBehaviour
{
    public int level = 1;
    public int xp = 0;

    // Simple thresholds: 200, 300, 400...
    public int BaseThreshold = 200;
    public int ThresholdStep = 100;

    public int GetThreshold(int forLevel)
    {
        return BaseThreshold + (forLevel - 1) * ThresholdStep;
    }

    public void AddXP(int amount)
    {
        xp = Mathf.Max(0, xp + amount);
        while (xp >= GetThreshold(level))
        {
            xp -= GetThreshold(level);
            level++;
        }
    }
}

