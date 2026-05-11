using UnityEngine;
using UnityEngine.SceneManagement;

public class AudioManager : MonoBehaviour
{
    public static AudioManager Instance;

    [Header("Music Clips")]
    public AudioClip mainMenuMusic;
    public AudioClip level1Music;
    public AudioClip level2EasyMusic;
    public AudioClip level2HardMusic;
    public AudioClip resultSceneMusic;

    [Header("Scene Names")]
    public string mainMenuSceneName = "MainMenu";
    public string level1SceneName = "Level1";
    public string level2EasySceneName = "Level2_Easy";
    public string level2HardSceneName = "Level2_Hard";
    public string resultSceneName = "ResultScene";

    private AudioSource musicSource;

    void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);

        musicSource = GetComponent<AudioSource>();

        if (musicSource == null)
        {
            musicSource = gameObject.AddComponent<AudioSource>();
        }

        musicSource.loop = true;
    }

    void OnEnable()
    {
        SceneManager.sceneLoaded += OnSceneLoaded;
    }

    void OnDisable()
    {
        SceneManager.sceneLoaded -= OnSceneLoaded;
    }

    void Start()
    {
        UpdateMusicForScene(SceneManager.GetActiveScene().name);
    }

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        UpdateMusicForScene(scene.name);
    }

    private void UpdateMusicForScene(string sceneName)
    {
        AudioClip targetClip = null;

        if (sceneName == mainMenuSceneName)
        {
            targetClip = mainMenuMusic;
        }
        else if (sceneName == level1SceneName)
        {
            targetClip = level1Music;
        }
        else if (sceneName == level2EasySceneName)
        {
            targetClip = level2EasyMusic;
        }
        else if (sceneName == level2HardSceneName)
        {
            targetClip = level2HardMusic;
        }
        else if (sceneName == resultSceneName)
        {
            targetClip = resultSceneMusic;
        }

        if (targetClip != null)
        {
            PlayMusic(targetClip);
        }
    }

    public void PlayMusic(AudioClip clip)
    {
        if (clip == null)
            return;

        if (musicSource.clip == clip && musicSource.isPlaying)
            return;

        musicSource.Stop();
        musicSource.clip = clip;
        musicSource.Play();
    }

    public void StopMusic()
    {
        if (musicSource != null)
        {
            musicSource.Stop();
        }
    }

    public void ToggleMute()
    {
        if (musicSource != null)
        {
            musicSource.mute = !musicSource.mute;
        }
    }

    public bool IsMuted()
    {
        return musicSource != null && musicSource.mute;
    }
}
