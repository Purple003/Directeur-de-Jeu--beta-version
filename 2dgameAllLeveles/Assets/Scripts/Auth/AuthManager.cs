using UnityEngine;
using TMPro;
using UnityEngine.SceneManagement;

public class AuthManager : MonoBehaviour
{
    public TMP_InputField usernameInput;
    public TMP_InputField passwordInput;
    public TMP_Text errorText;

    [Header("Scene Flow")]
    public string menuSceneName = "CourseScene"; // rename to PlayerMenuScene if you create it

    public void Login()
    {
        string username = usernameInput.text;
        string password = passwordInput.text;

        if (errorText != null) errorText.text = "";
        StartCoroutine(APIManager.Instance.Login(username, password, OnLoginResponse));
    }

    void OnLoginResponse(bool ok, string err)
    {
        if (!ok)
        {
            if (errorText != null) errorText.text = err;
            return;
        }

        SceneManager.LoadScene(menuSceneName);
    }
}
