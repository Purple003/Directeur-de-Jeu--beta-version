using UnityEngine;
using UnityEngine.UI;

public class HeartUIManager : MonoBehaviour
{
    [Header("Hearts (left to right)")]
    public Image[] hearts;
    public Sprite fullHeartSprite;
    public Sprite emptyHeartSprite;

    [Header("Game Over")]
    public GameObject gameOverPanel;
    public Button goToResultsButton;

    private GameManager gm;

    void OnEnable()
    {
        gm = FindObjectOfType<GameManager>();
        if (gm != null)
        {
            gm.OnHealthChanged += HandleHealthChanged;
            gm.OnGameOver += HandleGameOver;
            HandleHealthChanged(gm.CurrentHealth);
        }

        if (gameOverPanel != null) gameOverPanel.SetActive(false);
        if (goToResultsButton != null)
        {
            goToResultsButton.onClick.RemoveAllListeners();
            goToResultsButton.onClick.AddListener(() =>
            {
                if (gm != null) gm.CompleteLevel(); // loads ResultScene via existing flow
            });
        }
    }

    void OnDisable()
    {
        if (gm != null)
        {
            gm.OnHealthChanged -= HandleHealthChanged;
            gm.OnGameOver -= HandleGameOver;
        }
    }

    void HandleHealthChanged(int hp)
    {
        if (hearts == null) return;

        for (int i = 0; i < hearts.Length; i++)
        {
            Image img = hearts[i];
            if (img == null) continue;

            bool filled = i < hp;
            if (fullHeartSprite != null && emptyHeartSprite != null)
            {
                img.sprite = filled ? fullHeartSprite : emptyHeartSprite;
                img.enabled = true;
            }
            else
            {
                img.enabled = filled;
            }
        }
    }

    void HandleGameOver()
    {
        if (gameOverPanel != null) gameOverPanel.SetActive(true);
    }
}

