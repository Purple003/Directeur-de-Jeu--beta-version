using System;
using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;

public class GameManager : MonoBehaviour
{
    public static GameManager Instance { get; private set; }

    // Simple difficulty configuration for per-level starting hearts.
    // This is intentionally lightweight and does not change GameManager
    // lifecycle or persistence. It only maps a difficulty level to the
    // existing `startingHealth` value so scene loads and retries can
    // restore a difficulty-appropriate number of hearts.
    public enum Difficulty { Easy, Medium, Hard }

    [Header("Difficulty")]
    public Difficulty currentDifficulty = Difficulty.Medium;

    [Header("Scene Flow")]
    public string resultSceneName = "ResultScene";

    [Header("Session")]
    private int courseId = 0;
    private int sessionId = 0;
    private bool courseIdLocked = false;

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
    private bool startSessionCalled = false;

    public int CurrentHealth => health;
    public int CourseId => courseId;
    public int GetSessionId() => sessionId;

    public event Action<int> OnHealthChanged;
    public event Action OnGameOver;

    /// <summary>
    /// Sets courseId once per session. Immutable after StartSession.
    /// </summary>
    public void SetCourseId(int newCourseId)
    {
        if (courseIdLocked)
        {
            Debug.LogWarning($"[WARNING] courseId mutation blocked. Current: {courseId}, Attempted: {newCourseId}");
            return;
        }
        
        if (newCourseId <= 0)
        {
            Debug.LogError($"[Game] Invalid courseId {newCourseId}. Must be > 0.");
            return;
        }
        
        courseId = newCourseId;
        Debug.Log($"[Game] courseId set to {courseId}");
    }

    /// <summary>
    /// Locks courseId to prevent further changes during session.
    /// </summary>
    private void LockCourseId()
    {
        if (courseIdLocked)
        {
            Debug.LogWarning($"[Game] courseId already locked to {courseId}");
            return;
        }
        
        if (courseId <= 0)
        {
            Debug.LogError("[Game] Cannot lock invalid courseId (<= 0)");
            return;
        }
        
        courseIdLocked = true;
        Debug.Log($"[Game] courseId LOCKED = {courseId}");
    }

    public bool IsReadyForQuiz()
    {
        return bootstrapped
            && !bootstrapping
            && !endingSession
            && !quizOpen
            && GetSessionId() > 0
            && APIManager.Instance != null;
    }

    // Session stats (for ResultScene)
    private int correctCount = 0;
    private int totalAnswered = 0;
    private int sessionXpGained = 0;
    private int sessionStarsGained = 0;

    void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Debug.LogWarning($"[SYNC] Duplicate GameManager detected. Keeping instance {Instance.GetInstanceID()} and destroying {GetInstanceID()}");
            Destroy(gameObject);
            return;
        }
        Instance = this;
        DontDestroyOnLoad(gameObject);
        SceneManager.sceneLoaded += OnSceneLoaded;
        Debug.Log($"[SYNC] GameManager assigned instanceId={GetInstanceID()} and marked DontDestroyOnLoad");
        LogRuntimeState("Awake");
    }

    void OnDestroy()
    {
        if (Instance == this) Instance = null;
        SceneManager.sceneLoaded -= OnSceneLoaded;
    }

    void Start()
    {
        // Ensure the configured difficulty value is applied before any
        // runtime health initialization. This keeps the existing
        // `startingHealth` field as the authoritative source used
        // elsewhere in the codebase while allowing difficulty to
        // control its value in a safe, centralized place.
        ApplyDifficultyToStartingHealth();

        health = Mathf.Max(1, startingHealth);
        if (enemyManager == null) enemyManager = FindObjectOfType<EnemyManager>();
        UpdateHUD();
        OnHealthChanged?.Invoke(health);
        LogRuntimeState("Start");
        // NOTE: Do not auto-start session here. Session must begin AFTER course selection.
        if (!startSessionCalled && GetSessionId() <= 0)
        {
            Debug.Log("[SYNC] Session not started automatically. Waiting for explicit StartSession() call after course selection.");
        }
        else
        {
            bootstrapped = GetSessionId() > 0;
            Debug.Log($"[SYNC] Reusing persistent GameManager sessionId={GetSessionId()} startSessionCalled={startSessionCalled}");
        }
    }

    IEnumerator BootstrapSession()
    {
        if (bootstrapping) yield break;
        if (startSessionCalled)
        {
            Debug.Log($"[SYNC] BootstrapSession skipped: startSessionCalled=true sessionId={GetSessionId()}");
            bootstrapped = GetSessionId() > 0;
            yield break;
        }
        if (GetSessionId() > 0)
        {
            Debug.Log($"[SYNC] BootstrapSession skipped: existing sessionId={GetSessionId()}");
            // session already active; ensure startSessionCalled reflects that state (SetActiveSessionId normally does this)
            startSessionCalled = true;
            bootstrapped = true;
            yield break;
        }
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

        // Validate courseId is set (should be set by CourseMenuManager)
        if (courseId <= 0)
        {
            Debug.LogError("[Game] courseId not set. Go back to menu and select a course.");
            bootstrapping = false;
            yield break;
        }

        LogRuntimeState("BootstrapSession before StartSession");

        bool ok = false;
        string err = "";

        // Start session (bootstrapping prevents concurrent attempts)
        LogRuntimeState("BootstrapSession: invoking StartSession");
        yield return APIManager.Instance.StartSession(
            st.playerId,
            courseId,
            (sid) => { 
                SetActiveSessionId(sid);
                LockCourseId(); // Lock courseId for this session
                ok = true; 
            },
            (e) => { ok = false; err = e; }
        );
        if (!ok)
        {
            Debug.LogError("[Game] StartSession failed: " + err);
            startSessionCalled = false;
            bootstrapping = false;
            yield break;
        }

        Debug.Log($"[Game] Session STARTED with courseId {courseId}");
        LogRuntimeState("BootstrapSession after StartSession success");
        
        // Backend controls question selection per quiz trigger.
        bootstrapped = true;
        UpdateHUD();
        bootstrapping = false;
    }

    /// <summary>
    /// Public wrapper to start a session. Can be yielded by callers (e.g. CourseMenuManager).
    /// Returns after bootstrap completes (success or failure). Caller may inspect GetSessionId() / startSessionCalled.
    /// </summary>
    public IEnumerator StartSession()
    {
        // Delegate to existing bootstrap logic; BootstrapSession already guards against concurrent calls.
        yield return BootstrapSession();
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

        int activeSessionId = GetSessionId();
        if (activeSessionId <= 0 || APIManager.Instance == null)
        {
            quizOpen = false;
            yield break;
        }

        bool ok = false;
        string err = "";
        APIManager.GameQuestion q = null;

        Debug.Log($"[SYNC] Using sessionId={activeSessionId} courseId={courseId}");
        yield return APIManager.Instance.GetNextQuestion(
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

        // If this quiz was triggered by an enemy, disable its collider now that
        // the UI is shown. We disable the collider here (after ShowQuiz) so
        // physics is already paused by the UI (ShowQuiz sets Time.timeScale=0).
        // This avoids disabling the collider earlier during the async
        // GetNextQuestion call (which allowed the enemy to fall through ground).
        if (pendingEnemy != null)
        {
            Collider2D pendCol = pendingEnemy.GetComponent<Collider2D>();
            if (pendCol != null) pendCol.enabled = false;
        }
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

        OnHealthChanged?.Invoke(health);
        UpdateHUD();

        if (health <= 0)
        {
            Debug.Log("[Game] Health reached 0 -> ending run immediately.");
            EndRunToResults();
            return;
        }
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

        int activeSessionId = GetSessionId();
        Debug.Log($"[Game] EndSession start playerId={st.playerId} courseId={courseId} sessionId={activeSessionId} correct={correctCount} total={totalAnswered}");

        if (activeSessionId > 0)
        {
            bool ok = false;
            string err = "";
            yield return APIManager.Instance.EndSession(
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

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        // Reset scene-local references while keeping session state intact.
        ResetActiveSessionReferences();
        
        // Auto-detect difficulty from scene name to sync the enum value with
        // the level being loaded. This is the minimal fix for the bug where
        // `SetDifficulty()` is never called explicitly. Scene naming convention:
        // - "Level*_Easy" => Difficulty.Easy (5 hearts)
        // - "Level*_Hard" => Difficulty.Hard (2 hearts)
        // - Everything else (Level1, Level2, GameScene, etc) => Difficulty.Medium (3 hearts)
        string sceneName = scene.name.ToLower();
        if (sceneName.Contains("easy"))
        {
            currentDifficulty = Difficulty.Easy;
            Debug.Log($"[GameManager] Scene '{scene.name}' detected as Easy difficulty.");
        }
        else if (sceneName.Contains("hard"))
        {
            currentDifficulty = Difficulty.Hard;
            Debug.Log($"[GameManager] Scene '{scene.name}' detected as Hard difficulty.");
        }
        else
        {
            currentDifficulty = Difficulty.Medium;
            Debug.Log($"[GameManager] Scene '{scene.name}' detected as Medium difficulty (default).");
        }
        
        // Apply difficulty mapping and restore runtime health to the
        // configured per-level `startingHealth`. Because GameManager is
        // persistent across scenes (`DontDestroyOnLoad`), `Start()` will
        // not run again on reloads — so we re-apply the difficulty here
        // and reset the runtime `health` for retries/scene loads.
        ApplyDifficultyToStartingHealth();
        health = Mathf.Max(1, startingHealth);
        UpdateHUD();
        OnHealthChanged?.Invoke(health);
        LogRuntimeState($"SceneLoaded mode={mode} difficulty={currentDifficulty}");
    }

    /// <summary>
    /// Map `currentDifficulty` to the `startingHealth` used throughout
    /// the existing codebase. This keeps the change minimal: other
    /// systems continue to read `startingHealth` and runtime `health`.
    /// </summary>
    public void ApplyDifficultyToStartingHealth()
    {
        int oldHealth = startingHealth;
        switch (currentDifficulty)
        {
            case Difficulty.Easy:
                startingHealth = 5;
                break;
            case Difficulty.Medium:
                startingHealth = 3;
                break;
            case Difficulty.Hard:
                startingHealth = 2;
                break;
            default:
                startingHealth = 3;
                break;
        }
        Debug.Log($"[GameManager] ApplyDifficultyToStartingHealth: {currentDifficulty} => startingHealth changed from {oldHealth} to {startingHealth}");
    }

    /// <summary>
    /// Public setter for difficulty so external systems (menus, level
    /// selectors) can change difficulty before a level loads. If
    /// `applyImmediately` is true, `startingHealth` is updated
    /// immediately so subsequent scene loads will reset to that value.
    /// </summary>
    public void SetDifficulty(Difficulty d, bool applyImmediately = true)
    {
        currentDifficulty = d;
        if (applyImmediately) ApplyDifficultyToStartingHealth();
    }

    private void LogRuntimeState(string context)
    {
        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        string sceneName = SceneManager.GetActiveScene().name;
        int playerIdValue = st != null ? st.playerId : 0;
        int sessionIdValue = GetSessionId();
        Debug.Log(
            $"[GameState] {context} | " +
            $"playerId={playerIdValue} | " +
            $"courseId={courseId} | " +
            $"sessionId={sessionIdValue} | " +
            $"gameManagerInstanceId={GetInstanceID()} | " +
            $"sceneName={sceneName} | " +
            $"startSessionCalled={startSessionCalled}"
        );
    }

    private void SetActiveSessionId(int newSessionId)
    {
        if (newSessionId <= 0)
        {
            Debug.LogWarning($"[SYNC] Ignoring invalid sessionId assignment: {newSessionId}");
            return;
        }

        if (sessionId > 0 && sessionId != newSessionId)
        {
            Debug.LogWarning($"[SYNC] Session already assigned ({sessionId}); ignoring reassignment to {newSessionId}");
            return;
        }

        sessionId = newSessionId;
        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st != null) st.sessionId = sessionId;
        startSessionCalled = true;
        Debug.Log($"[SYNC] GameManager sessionId updated to {sessionId} for courseId={courseId}");
    }

    private void ResetActiveSessionReferences()
    {
        DialogueManager dialogueManager = FindObjectOfType<DialogueManager>();
        if (dialogueManager != null) dialogueManager.ResetBackendState();
        // Rebind common scene-local references that may have been lost on scene load.
        EnemyManager em = FindObjectOfType<EnemyManager>();
        if (em != null) enemyManager = em;

        QuizUIManager qm = FindObjectOfType<QuizUIManager>();
        if (qm != null) quizUI = qm;

        TMP_Text[] texts = FindObjectsOfType<TMP_Text>();
        foreach (var t in texts)
        {
            if (t.name == "HUDText" || t.name.ToLower().Contains("hud")) hudText = t;
            if (t.name == "HealthText" || t.name.ToLower().Contains("health")) healthText = t;
        }

        Debug.Log($"[SYNC] Reset scene references. sessionId remains {sessionId} | enemyManager={(enemyManager!=null)} quizUI={(quizUI!=null)} hudText={(hudText!=null)} healthText={(healthText!=null)}");
    }
}
