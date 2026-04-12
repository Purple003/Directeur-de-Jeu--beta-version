using UnityEngine;
using UnityEngine.SceneManagement;

public class StartUIManager : MonoBehaviour
{
    public string levelSceneName = "Level1";

    public void OnStartButton()
    {
        SceneManager.LoadScene(levelSceneName);
    }
}