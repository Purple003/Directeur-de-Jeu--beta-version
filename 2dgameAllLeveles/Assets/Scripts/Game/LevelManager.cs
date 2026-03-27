using UnityEngine;
using UnityEngine.SceneManagement;

// Minimal level unlock helper (stars-based). Scene loading is optional and configurable.
public class LevelManager : MonoBehaviour
{
    [Header("Scenes")]
    public string[] levelScenes = new string[] { "GameScene" };

    [Header("Unlock Rules")]
    // Level 1 always unlocked. Each next level requires N stars.
    public int starsPerUnlock = 3;

    public int GetUnlockedLevelsCount()
    {
        // Ensure state exists even if this scene is loaded directly.
        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        int stars = (st != null) ? Mathf.Max(0, st.stars) : 0;
        int unlocked = 1 + (starsPerUnlock > 0 ? (stars / starsPerUnlock) : 0);
        return Mathf.Clamp(unlocked, 1, Mathf.Max(1, levelScenes.Length));
    }

    public bool IsLevelUnlocked(int levelIndex0)
    {
        return levelIndex0 >= 0 && levelIndex0 < GetUnlockedLevelsCount();
    }

    public void LoadLevel(int levelIndex0)
    {
        if (!IsLevelUnlocked(levelIndex0)) return;
        if (levelScenes == null || levelScenes.Length == 0) return;
        string scene = levelScenes[Mathf.Clamp(levelIndex0, 0, levelScenes.Length - 1)];
        if (!string.IsNullOrEmpty(scene)) SceneManager.LoadScene(scene);
    }
}
