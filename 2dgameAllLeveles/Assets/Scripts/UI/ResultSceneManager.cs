using UnityEngine;
using TMPro;
using UnityEngine.SceneManagement;

// Attach this to ResultScene. Shows the last session results stored in PlayerSessionState.
public class ResultSceneManager : MonoBehaviour
{
    public TMP_Text summaryText;

    [Header("Scene Flow")]
    public string menuSceneName = "CourseScene";
    public string gameSceneName = "GameScene";

    void Start()
    {
        // Safety: ensure we are not left paused if gameplay ended while QuizUI had timeScale=0.
        Time.timeScale = 1f;

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (summaryText == null) return;

        if (st == null)
        {
            summaryText.text = "No results.";
            return;
        }

        float accuracy = (st.lastTotal > 0) ? (100f * st.lastCorrect / Mathf.Max(1, st.lastTotal)) : 0f;

        GameManager gameManager = FindObjectOfType<GameManager>();
        int courseId = (gameManager != null) ? gameManager.CourseId : 0;
        
        summaryText.text =
            $"Course: {courseId}\n" +
            $"Score: {st.lastFinalScore:0.0}%\n" +
            $"Accuracy: {accuracy:0.0}% ({st.lastCorrect}/{Mathf.Max(1, st.lastTotal)})\n" +
            $"Duration: {st.lastDurationMs} ms\n" +
            $"XP Gained: {st.lastXpGained}\n" +
            $"Stars Gained: {st.lastStarsGained}\n" +
            $"Next Level: {st.lastNextLevel}\n" +
            $"Recommended difficulty: {st.lastRecommendedDifficulty}\n";
    }

    public void BackToMenu()
    {
        SceneManager.LoadScene(menuSceneName);
    }

    public void PlayAgain()
    {
        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null) { SceneManager.LoadScene(gameSceneName); return; }

        string diff = (st.lastRecommendedDifficulty ?? "").ToLower().Trim();
        
        // Adaptive level selection based on recommended difficulty
        if (diff == "easy")
            SceneManager.LoadScene("Level2_Easy");
        else if (diff == "hard")
            SceneManager.LoadScene("Level2_Hard");
        else
            SceneManager.LoadScene(gameSceneName); // medium = same level
    }
}
