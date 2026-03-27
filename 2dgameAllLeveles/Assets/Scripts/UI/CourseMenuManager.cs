using UnityEngine;
using TMPro;
using UnityEngine.SceneManagement;

// Attach this to CourseScene (menu). It creates/loads a player and starts the game.
public class CourseMenuManager : MonoBehaviour
{
    const string PREF_PLAYER_ID = "asg_player_id";
    const string PREF_COURSE_ID = "asg_course_id";

    [Header("Inputs")]
    public TMP_InputField playerIdInput;
    public TMP_InputField playerNameInput;
    public TMP_InputField courseIdInput;

    [Header("Display")]
    public TMP_Text playerInfoText;
    public TMP_Text errorText;

    [Header("Scene Flow")]
    public string gameSceneName = "GameScene";
    public string loginSceneName = "LoginScene";

    private bool loadingPlayer = false;
    private bool startingGame = false;

    void Start()
    {
        // Make state stable even if CourseScene is not the first scene loaded.
        PlayerSessionState.EnsureInstance();
        APIManager.EnsureInstance();

        LoadPrefsIntoUI();
        RefreshUI();

        // If we already have a playerId saved, refresh profile from backend.
        PlayerSessionState st = PlayerSessionState.Instance;
        if (st != null && st.playerId > 0 && APIManager.Instance != null)
        {
            // Mark as loading to avoid race with StartGame button.
            StartCoroutine(LoadPlayerRoutine(st.playerId, onLoaded: null));
        }
    }

    public void CreatePlayer()
    {
        ClearError();
        if (APIManager.EnsureInstance() == null) { SetError("[CourseMenu] APIManager missing."); return; }
        if (loadingPlayer) { SetError("[CourseMenu] Loading player..."); return; }

        string name = (playerNameInput != null) ? playerNameInput.text : "";
        if (string.IsNullOrWhiteSpace(name)) { SetError("[CourseMenu] Enter player name."); return; }

        loadingPlayer = true;
        StartCoroutine(APIManager.Instance.CreatePlayer(
            name.Trim(),
            null,
            "",
            "",
            (playerId) =>
            {
                PlayerSessionState st = PlayerSessionState.Instance;
                if (st != null) st.playerId = playerId;
                if (playerIdInput != null) playerIdInput.text = playerId.ToString();
                SavePlayerIdPref(playerId);
                loadingPlayer = false;
                LoadPlayer(); // refresh profile from backend
            },
            (err) => { loadingPlayer = false; SetError(err); }
        ));
    }

    public void LoadPlayer()
    {
        ClearError();
        if (APIManager.EnsureInstance() == null) { SetError("[CourseMenu] APIManager missing."); return; }

        if (loadingPlayer) { SetError("[CourseMenu] Loading player..."); return; }

        int id = ResolvePlayerIdFromUIOrState();
        if (id <= 0) { SetError("[CourseMenu] Enter a valid player id (or create a player)."); return; }

        StartCoroutine(LoadPlayerRoutine(id, onLoaded: null));
    }

    public void StartGame()
    {
        ClearError();
        if (startingGame) { SetError("[CourseMenu] Starting game..."); return; }
        if (loadingPlayer) { SetError("[CourseMenu] Loading player..."); return; }
        StartCoroutine(StartGameRoutine());
    }

    System.Collections.IEnumerator StartGameRoutine()
    {
        startingGame = true;

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null) { SetError("[CourseMenu] PlayerSessionState missing."); startingGame = false; yield break; }
        if (APIManager.EnsureInstance() == null) { SetError("[CourseMenu] APIManager missing."); startingGame = false; yield break; }

        int id = ResolvePlayerIdFromUIOrState();
        if (id <= 0) { SetError("[CourseMenu] Create or load a player first."); startingGame = false; yield break; }

        // Ensure the profile is actually loaded before entering GameScene (prevents race conditions).
        if (st.playerId != id || string.IsNullOrEmpty(st.playerName))
        {
            string err = "";
            yield return LoadPlayerRoutine(id, onLoaded: null, onErr: (e) => { err = e; });
            if (!string.IsNullOrEmpty(err))
            {
                SetError(err);
                startingGame = false;
                yield break;
            }
        }

        int courseId = ResolveCourseIdFromUIOrState();
        st.courseId = courseId;
        SaveCourseIdPref(courseId);
        SavePlayerIdPref(id);

        Debug.Log($"[CourseMenu] StartGame playerId={st.playerId} courseId={st.courseId} name='{st.playerName}'");
        SceneManager.LoadScene(gameSceneName);
        startingGame = false;
    }

    public void LogoutToLogin()
    {
        SceneManager.LoadScene(loginSceneName);
    }

    void RefreshUI()
    {
        PlayerSessionState st = PlayerSessionState.Instance;
        if (st == null)
        {
            if (playerInfoText != null) playerInfoText.text = "No session state.";
            return;
        }

        if (playerInfoText != null)
        {
            playerInfoText.text =
                $"Player: {st.playerId} {st.playerName}\n" +
                $"Level: {st.gameLevel}\n" +
                $"XP: {st.xp}\n" +
                $"Stars: {st.stars}\n" +
                $"Course: {st.courseId}";
        }

        if (courseIdInput != null && string.IsNullOrEmpty(courseIdInput.text))
        {
            courseIdInput.text = st.courseId.ToString();
        }
        if (playerIdInput != null && string.IsNullOrEmpty(playerIdInput.text) && st.playerId > 0)
        {
            playerIdInput.text = st.playerId.ToString();
        }
    }

    void ClearError()
    {
        if (errorText != null) errorText.text = "";
    }

    void SetError(string msg)
    {
        if (errorText != null) errorText.text = msg;
        // Keep all menu logs tagged consistently.
        Debug.LogWarning(string.IsNullOrEmpty(msg) ? "[CourseMenu] (empty error)" : (msg.StartsWith("[CourseMenu]") ? msg : "[CourseMenu] " + msg));
    }

    int ResolvePlayerIdFromUIOrState()
    {
        PlayerSessionState st = PlayerSessionState.Instance;
        int id = 0;
        string raw = (playerIdInput != null) ? (playerIdInput.text ?? "").Trim() : "";
        if (!string.IsNullOrEmpty(raw))
        {
            int.TryParse(raw, out id);
        }
        if (id <= 0 && st != null && st.playerId > 0) id = st.playerId;
        return id;
    }

    int ResolveCourseIdFromUIOrState()
    {
        PlayerSessionState st = PlayerSessionState.Instance;
        int id = (st != null && st.courseId > 0) ? st.courseId : 1;
        string raw = (courseIdInput != null) ? (courseIdInput.text ?? "").Trim() : "";
        if (!string.IsNullOrEmpty(raw))
        {
            int.TryParse(raw, out id);
        }
        if (id <= 0) id = 1;
        return id;
    }

    System.Collections.IEnumerator LoadPlayerRoutine(int id, System.Action onLoaded, System.Action<string> onErr = null)
    {
        loadingPlayer = true;
        Debug.Log($"[CourseMenu] LoadPlayer id={id}");

        yield return APIManager.Instance.GetPlayer(
            id,
            (p) =>
            {
                PlayerSessionState st = PlayerSessionState.Instance;
                if (st != null) st.ApplyBackendProfile(p);
                if (playerIdInput != null) playerIdInput.text = id.ToString();
                SavePlayerIdPref(id);
                RefreshUI();
                onLoaded?.Invoke();
            },
            (err) =>
            {
                onErr?.Invoke(err);
                SetError(err);
            }
        );

        loadingPlayer = false;
    }

    void LoadPrefsIntoUI()
    {
        int pid = PlayerPrefs.GetInt(PREF_PLAYER_ID, 0);
        int cid = PlayerPrefs.GetInt(PREF_COURSE_ID, 1);
        if (playerIdInput != null && string.IsNullOrEmpty(playerIdInput.text) && pid > 0) playerIdInput.text = pid.ToString();
        if (courseIdInput != null && string.IsNullOrEmpty(courseIdInput.text) && cid > 0) courseIdInput.text = cid.ToString();

        PlayerSessionState st = PlayerSessionState.Instance;
        if (st != null)
        {
            if (st.playerId <= 0 && pid > 0) st.playerId = pid;
            if (st.courseId <= 0 && cid > 0) st.courseId = cid;
        }
    }

    void SavePlayerIdPref(int id)
    {
        if (id <= 0) return;
        PlayerPrefs.SetInt(PREF_PLAYER_ID, id);
        PlayerPrefs.Save();
    }

    void SaveCourseIdPref(int id)
    {
        if (id <= 0) return;
        PlayerPrefs.SetInt(PREF_COURSE_ID, id);
        PlayerPrefs.Save();
    }
}
