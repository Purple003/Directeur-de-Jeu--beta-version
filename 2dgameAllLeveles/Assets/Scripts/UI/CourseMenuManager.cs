using UnityEngine;
using TMPro;
using UnityEngine.SceneManagement;
using System.Collections;
using System.Collections.Generic;

// Attach this to CourseScene (menu). It creates/loads a player and starts the game.
public class CourseMenuManager : MonoBehaviour
{
    const string PREF_PLAYER_ID = "asg_player_id";

    [Header("Inputs")]
    public TMP_InputField playerIdInput;
    public TMP_InputField playerNameInput;
    public TMP_Dropdown courseDropdown;

    [Header("Display")]
    public TMP_Text playerInfoText;
    public TMP_Text errorText;

    [Header("Scene Flow")]
    public string gameSceneName = "GameScene";
    public string loginSceneName = "LoginScene";

    private bool loadingPlayer = false;
    private bool startingGame = false;
    private bool loadingCourses = false;
    private int selectedCourseId = 0;
    private APIManager.CourseSummary[] loadedCourses = new APIManager.CourseSummary[0];

    void Start()
    {
        // Make state stable even if CourseScene is not the first scene loaded.
        PlayerSessionState.EnsureInstance();
        APIManager.EnsureInstance();

        if (courseDropdown == null)
        {
            SetError("[CourseMenu] courseDropdown is not assigned in the inspector.");
        }

        LoadPrefsIntoUI();
        RefreshUI();

        LoadCourses();
        StartCoroutine(EnsurePlayerExists());
    }

    public void LoadCourses()
    {
        if (loadingCourses) return;
        if (APIManager.EnsureInstance() == null) { SetError("[CourseMenu] APIManager missing."); return; }
        if (courseDropdown == null) { SetError("[CourseMenu] courseDropdown is not assigned."); return; }
        Debug.Log("[CourseMenu] LoadCourses triggered.");
        StartCoroutine(LoadCoursesRoutine());
    }

    private IEnumerator EnsurePlayerExists()
    {
        PlayerSessionState st = PlayerSessionState.Instance;

        if (st.playerId > 0)
        {
            yield return LoadPlayerRoutine(st.playerId, null);
            yield break;
        }

        bool done = false;

        yield return APIManager.Instance.CreatePlayer(
            "Player_" + System.DateTime.Now.Ticks,
            null,
            "",
            "",
            (newId) =>
            {
                st.playerId = newId;
                PlayerPrefs.SetInt("asg_player_id", newId);
                PlayerPrefs.Save();
                done = true;
            },
            (err) =>
            {
                Debug.LogError("Create player failed: " + err);
                done = true;
            }
        );

        while (!done) yield return null;
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
        Debug.Log("[CourseMenu] StartGame button pressed.");
        if (startingGame) { SetError("[CourseMenu] Starting game..."); return; }
        if (loadingPlayer) { SetError("[CourseMenu] Loading player..."); return; }
        if (loadingCourses) { SetError("[CourseMenu] Loading courses..."); return; }
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

        int courseId = ResolveSelectedCourseId();
        if (courseId <= 0)
        {
            SetError("[CourseMenu] Select a course first.");
            startingGame = false;
            yield break;
        }
        
        // Set courseId in GameManager (single source of truth)
        GameManager gameManager = FindObjectOfType<GameManager>();
        if (gameManager != null)
        {
            gameManager.SetCourseId(courseId);
        }
        else
        {
            Debug.LogError("[CourseMenu] GameManager not found. Cannot set courseId.");
            startingGame = false;
            yield break;
        }
        
        // Start session now that courseId is set. Wait for session init to complete.
        yield return gameManager.StartSession();
        if (gameManager.GetSessionId() <= 0)
        {
            SetError("Failed to start session. See logs for details.");
            startingGame = false;
            yield break;
        }

        // Persist selected course and player id only after successful session start.
        SavePlayerIdPref(id);
        PlayerPrefs.SetInt("selectedCourseId", selectedCourseId);
        PlayerPrefs.Save();
        Debug.Log($"[Flow] Saved courseId = {selectedCourseId}");

        Debug.Log($"[CourseMenu] StartGame playerId={st.playerId} courseId={courseId} sessionId={gameManager.GetSessionId()} name='{st.playerName}'");
        SceneManager.LoadScene("Level1");
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
                $"Stars: {st.stars}";
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

    int ResolveSelectedCourseId()
    {
        if (selectedCourseId > 0) return selectedCourseId;
        if (courseDropdown == null || loadedCourses == null || loadedCourses.Length == 0) return 0;

        int optionIndex = courseDropdown.value - 1;
        if (optionIndex < 0 || optionIndex >= loadedCourses.Length) return 0;
        APIManager.CourseSummary selected = loadedCourses[optionIndex];
        return selected != null ? selected.id : 0;
    }

    IEnumerator LoadCoursesRoutine()
    {
        loadingCourses = true;

        yield return APIManager.Instance.GetCourses(
            (courses) =>
            {
                loadedCourses = courses ?? new APIManager.CourseSummary[0];
                Debug.Log($"[CourseMenu] Courses loaded count={loadedCourses.Length} items={FormatCoursesForLog(loadedCourses)}");
                if (loadedCourses.Length == 0)
                {
                    SetError("[CourseMenu] No courses available from backend.");
                }
                PopulateCourseDropdown();
                loadingCourses = false;
            },
            (err) =>
            {
                loadedCourses = new APIManager.CourseSummary[0];
                loadingCourses = false;
                SetError(err);
            }
        );
    }

    void PopulateCourseDropdown()
    {
        if (courseDropdown == null)
        {
            SetError("[CourseMenu] courseDropdown is not assigned.");
            return;
        }

        // Rebuild the dropdown from scratch each time to avoid stale or duplicated entries.
        courseDropdown.onValueChanged.RemoveListener(OnCourseDropdownChanged);
        courseDropdown.ClearOptions();

        List<TMP_Dropdown.OptionData> options = new List<TMP_Dropdown.OptionData>();
        options.Add(new TMP_Dropdown.OptionData("Select course"));

        for (int i = 0; i < loadedCourses.Length; i++)
        {
            APIManager.CourseSummary course = loadedCourses[i];
            if (course == null || course.id <= 0) continue;
            options.Add(new TMP_Dropdown.OptionData(course.name));
        }

        courseDropdown.AddOptions(options);
        courseDropdown.value = 0;
        courseDropdown.RefreshShownValue();
        selectedCourseId = 0;
        courseDropdown.onValueChanged.AddListener(OnCourseDropdownChanged);
        Debug.Log($"[CourseMenu] Dropdown populated optionCount={options.Count} courseCount={loadedCourses.Length}");
    }

    public void OnCourseDropdownChanged(int selectedIndex)
    {
        if (selectedIndex <= 0 || loadedCourses == null || selectedIndex > loadedCourses.Length)
        {
            selectedCourseId = 0;
            Debug.Log("[CourseMenu] Course selection cleared.");
            return;
        }

        APIManager.CourseSummary selected = loadedCourses[selectedIndex - 1];
        selectedCourseId = (selected != null) ? selected.id : 0;
        Debug.Log($"[CourseMenu] Course selected dropdownIndex={selectedIndex} courseId={selectedCourseId} courseName='{(selected != null ? selected.name : "null")}'");

        GameManager gameManager = FindObjectOfType<GameManager>();
        if (gameManager != null && selectedCourseId > 0)
        {
            gameManager.SetCourseId(selectedCourseId);
        }
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
        if (playerIdInput != null && string.IsNullOrEmpty(playerIdInput.text) && pid > 0) playerIdInput.text = pid.ToString();

        PlayerSessionState st = PlayerSessionState.Instance;
        if (st != null)
        {
            if (st.playerId <= 0 && pid > 0) st.playerId = pid;
        }
    }

    void SavePlayerIdPref(int id)
    {
        if (id <= 0) return;
        PlayerPrefs.SetInt(PREF_PLAYER_ID, id);
        PlayerPrefs.Save();
    }

    string FormatCoursesForLog(APIManager.CourseSummary[] courses)
    {
        if (courses == null || courses.Length == 0) return "[]";

        System.Text.StringBuilder sb = new System.Text.StringBuilder();
        sb.Append("[");
        for (int i = 0; i < courses.Length; i++)
        {
            APIManager.CourseSummary c = courses[i];
            if (i > 0) sb.Append(", ");
            if (c == null) sb.Append("{null}");
            else sb.Append("{id=").Append(c.id).Append(", name=").Append(c.name).Append("}");
        }
        sb.Append("]");
        return sb.ToString();
    }
}
