using System;
using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;

public class GameManager : MonoBehaviour
{
    [Header("Scene Flow")]
    public string resultSceneName = "ResultScene";

    [Header("Session")]
    public int courseIdOverride = 0; // if 0, use PlayerSessionState.courseId

    [Header("Quiz")]
    public QuizUIManager quizUI;

    [Header("HUD (Optional)")]
    public TMP_Text hudText;
    public TMP_Text healthText;

    [Header("Gameplay")]
    public int startingHealth = 3;
    public EnemyManager enemyManager;

    [Header("Game Over")]
    public bool pauseOnGameOver = true;
    public float gameOverDelaySeconds = 1.25f;

    private int health;
    private bool bootstrapped = false;
    private bool endingSession = false;
    private bool quizOpen = false;
    private bool bootstrapping = false;
    private GameObject pendingEnemy = null;
    private Action onEnemyQuizClosed = null;
    private bool gameOverSequenceStarted = false;

    public int CurrentHealth => health;

    public event Action<int> OnHealthChanged;
    public event Action OnGameOver;

    public bool IsReadyForQuiz()
    {
        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        return bootstrapped
            && !bootstrapping
            && !endingSession
            && !quizOpen
            && st != null
            && st.sessionId > 0
            && APIManager.Instance != null;
    }

    // Session stats (for ResultScene)
    private int correctCount = 0;
    private int totalAnswered = 0;
    private int sessionXpGained = 0;
    private int sessionStarsGained = 0;

    void Start()
    {
        health = Mathf.Max(1, startingHealth);
        if (enemyManager == null) enemyManager = FindObjectOfType<EnemyManager>();
        UpdateHUD();
        OnHealthChanged?.Invoke(health);
        StartCoroutine(BootstrapSession());
    }

    IEnumerator BootstrapSession()
    {
        if (bootstrapping) yield break;
        bootstrapping = true;

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null)
        {
            Debug.LogError("[Game] PlayerSessionState missing in scene.");
            bootstrapping = false;
            yield break;
        }
        if (APIManager.EnsureInstance() == null)
        {
            Debug.LogError("[Game] APIManager missing in scene.");
            bootstrapping = false;
            yield break;
        }
        if (st.playerId <= 0)
        {
            Debug.LogError("[Game] No playerId set. Go back to menu and create/load a player.");
            bootstrapping = false;
            yield break;
        }

        int courseId = courseIdOverride > 0 ? courseIdOverride : st.courseId;
        if (courseId <= 0) courseId = 1;
        st.courseId = courseId;

        Debug.Log($"[Game] Bootstrap playerId={st.playerId} courseId={st.courseId} sessionId={st.sessionId}");

        bool ok = false;
        string err = "";

        // Start session
        yield return APIManager.Instance.StartSession(
            st.playerId,
            st.courseId,
            (sid) => { st.sessionId = sid; ok = true; },
            (e) => { ok = false; err = e; }
        );
        if (!ok)
        {
            Debug.LogError("[Game] StartSession failed: " + err);
            bootstrapping = false;
            yield break;
        }

        // Backend controls question selection per quiz trigger.
        bootstrapped = true;
        UpdateHUD();
        bootstrapping = false;
    }

    public void TriggerQuiz()
    {
        if (endingSession)
        {
            Debug.LogWarning("[Game] TriggerQuiz blocked: session is ending.");
            return;
        }
        if (quizOpen)
        {
            Debug.LogWarning("[Game] TriggerQuiz blocked: quiz already open.");
            return;
        }
        if (!bootstrapped)
        {
            Debug.LogWarning("[Game] TriggerQuiz blocked: game not ready yet (session/questions still loading).");
            return;
        }
        if (quizUI == null)
        {
            quizUI = FindObjectOfType<QuizUIManager>();
            if (quizUI == null)
            {
                Debug.LogError("[Game] QuizUIManager not found.");
                return;
            }
        }

        StartCoroutine(OpenNextQuestionQuiz());
    }

    public void TriggerQuizForEnemy(GameObject enemy, Action onClosed)
    {
        if (enemy == null)
        {
            TriggerQuiz();
            onClosed?.Invoke();
            return;
        }
        pendingEnemy = enemy;
        onEnemyQuizClosed = onClosed;
        TriggerQuiz();
    }

    IEnumerator OpenNextQuestionQuiz()
    {
        if (quizOpen) yield break;
        quizOpen = true;

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null || st.sessionId <= 0 || APIManager.Instance == null)
        {
            quizOpen = false;
            yield break;
        }

        bool ok = false;
        string err = "";
        APIManager.GameQuestion q = null;

        yield return APIManager.Instance.GetNextQuestion(
            st.sessionId,
            (qq) => { q = qq; ok = true; },
            (e) => { ok = false; err = e; }
        );

        if (!ok || q == null || q.id <= 0)
        {
            quizOpen = false;
            Debug.LogWarning("[Game] GetNextQuestion failed: " + err);
            // If no more questions, end the run gracefully.
            if (!string.IsNullOrEmpty(err) && err.ToLower().Contains("no more questions"))
            {
                EndRunToResults();
            }
            yield break;
        }

        // Show exactly one backend-chosen question (no randomness client-side).
        quizUI.ShowQuiz(new APIManager.GameQuestion[] { q }, OnQuizDone);
    }

    void OnQuizDone(bool isCorrect)
    {
        quizOpen = false;
        totalAnswered++;
        if (isCorrect)
        {
            correctCount++;
            AddXP(50);
            StartCoroutine(PushProgressDelta(xpDelta: 50, starsDelta: 0));

            if (pendingEnemy != null)
            {
                if (enemyManager == null) enemyManager = FindObjectOfType<EnemyManager>();
                if (enemyManager != null) enemyManager.DestroyEnemy(pendingEnemy);
                else Destroy(pendingEnemy);
            }
        }
        else
        {
            TakeDamage(1);
        }

        pendingEnemy = null;
        onEnemyQuizClosed?.Invoke();
        onEnemyQuizClosed = null;

        UpdateHUD();
    }

    public void AddXP(int amount)
    {
        sessionXpGained = Mathf.Max(0, sessionXpGained + amount);
    }

    public void AddStar(int amount)
    {
        sessionStarsGained = Mathf.Max(0, sessionStarsGained + amount);
    }

    public void TakeDamage(int amount)
    {
        health = Mathf.Max(0, health - Mathf.Max(0, amount));

        if (health <= 0)
        {
            // OPTION A: no-fail recovery
            health = Mathf.Max(1, startingHealth);

            if (enemyManager == null) enemyManager = FindObjectOfType<EnemyManager>();

            // Force adaptation immediately (ignore EmotionManager timing)
            AdaptationManager ad = null;
            if (enemyManager != null) ad = enemyManager.adaptation;
            if (ad == null) ad = FindObjectOfType<AdaptationManager>();
            if (ad != null) ad.ForceStressed(60f);

            // Remove current enemies for breathing space
            if (enemyManager != null) enemyManager.ClearAll();
        }

        OnHealthChanged?.Invoke(health);
        UpdateHUD();
    }

    IEnumerator GameOverSequence()
    {
        if (gameOverSequenceStarted) yield break;
        gameOverSequenceStarted = true;

        OnGameOver?.Invoke();

        if (pauseOnGameOver) Time.timeScale = 0f;

        float d = Mathf.Max(0f, gameOverDelaySeconds);
        if (d > 0f) yield return new WaitForSecondsRealtime(d);

        if (pauseOnGameOver) Time.timeScale = 1f;
        EndRunToResults();
    }

    IEnumerator PushProgressDelta(int xpDelta, int starsDelta)
    {
        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null || st.playerId <= 0) yield break;

        yield return APIManager.Instance.UpdateProgress(
            st.playerId,
            xpDelta,
            starsDelta,
            (resp) =>
            {
                st.xp = resp.xp;
                st.stars = resp.stars;
                st.gameLevel = resp.game_level;
            },
            (err) => Debug.LogWarning("[API] UpdateProgress failed: " + err)
        );
        UpdateHUD();
    }

    public void CompleteLevel()
    {
        EndRunToResults();
    }

    void EndRunToResults()
    {
        if (endingSession) return;
        StartCoroutine(EndSessionAndLoadResults());
    }

    IEnumerator EndSessionAndLoadResults()
    {
        endingSession = true;
        // Block quiz while ending; also avoids a late SubmitAnswer using a cleared sessionId.
        quizOpen = false;
        // Safety: ensure the game is not left paused if the quiz UI was open.
        Time.timeScale = 1f;

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null || APIManager.Instance == null)
        {
            SceneManager.LoadScene(resultSceneName);
            endingSession = false;
            yield break;
        }

        st.lastCorrect = correctCount;
        st.lastTotal = totalAnswered;
        st.lastXpGained = sessionXpGained;
        st.lastStarsGained = sessionStarsGained;

        Debug.Log($"[Game] EndSession start playerId={st.playerId} courseId={st.courseId} sessionId={st.sessionId} correct={correctCount} total={totalAnswered}");

        if (st.sessionId > 0)
        {
            bool ok = false;
            string err = "";
            yield return APIManager.Instance.EndSession(
                st.sessionId,
                (data) =>
                {
                    ok = true;
                    st.lastFinalScore = data.final_score;
                    st.lastDurationMs = data.duration_ms;
                    st.lastNextLevel = data.next_level;
                    st.lastRecommendedDifficulty = data.recommended_difficulty ?? "";
                },
                (e) => { ok = false; err = e; }
            );
            if (!ok)
            {
                Debug.LogWarning("[Game] EndSession failed: " + err);
            }
        }
        else
        {
            Debug.LogWarning("[Game] EndSession skipped: sessionId is missing (0).");
        }

        // Clear current session id so we don't accidentally reuse it.
        st.sessionId = 0;

        SceneManager.LoadScene(resultSceneName);
        endingSession = false;
    }

    void UpdateHUD()
    {
        PlayerSessionState st = PlayerSessionState.EnsureInstance();

        if (healthText != null) healthText.text = "HP: " + health;
        if (hudText != null)
        {
            string p = (st != null && st.playerId > 0) ? $"Player {st.playerId} L{st.gameLevel} XP {st.xp} Stars {st.stars}" : "No player";
            hudText.text = p + $"\nQuiz: {correctCount}/{totalAnswered}  +XP {sessionXpGained}";
        }
    }
}
