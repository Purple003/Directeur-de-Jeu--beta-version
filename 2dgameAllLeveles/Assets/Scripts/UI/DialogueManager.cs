using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using System.Collections;

public class DialogueManager : MonoBehaviour
{
    [Header("UI")]
    public GameObject panel;
    public TMP_Text dialogueText;
    public Button understoodButton;
    public Button repeatButton;
    public Button simplifyButton;

    [Header("Optional")]
    public EnemyManager enemyManager;
    public int enemiesToSpawnAfterDialogue = 5;

    private bool isOpen = false;
    private string lastDialogue = "";
    private string fallbackDialogue = "";
    private Action onUnderstood;

    // Backend dialogue mode (optional)
    private bool backendMode = false;
    private bool requestInFlight = false;
    private bool lastSimplify = false;

    void Awake()
    {
        WireButtons();
        SetOpen(false);
    }

    void WireButtons()
    {
        if (understoodButton != null)
        {
            understoodButton.onClick.RemoveAllListeners();
            understoodButton.onClick.AddListener(() => OnChoice("understood"));
        }
        if (repeatButton != null)
        {
            repeatButton.onClick.RemoveAllListeners();
            repeatButton.onClick.AddListener(() => OnChoice("repeat"));
        }
        if (simplifyButton != null)
        {
            simplifyButton.onClick.RemoveAllListeners();
            simplifyButton.onClick.AddListener(() => OnChoice("simplify"));
        }
    }

    public bool IsOpen => isOpen;

    public void ShowDialogue(string text, Action onUnderstoodCallback = null)
    {
        backendMode = false;
        lastDialogue = string.IsNullOrWhiteSpace(text) ? "..." : text;
        fallbackDialogue = lastDialogue;
        onUnderstood = onUnderstoodCallback;

        if (dialogueText != null) dialogueText.text = lastDialogue;
        SetOpen(true);
        Time.timeScale = 0f;
    }

    public void ShowBackendDialogue(string fallbackText = "", Action onUnderstoodCallback = null)
    {
        backendMode = true;
        fallbackDialogue = string.IsNullOrWhiteSpace(fallbackText) ? "..." : fallbackText;
        onUnderstood = onUnderstoodCallback;

        SetOpen(true);
        Time.timeScale = 0f;

        // Start by loading a fresh backend response.
        StartCoroutine(RequestDialogue(simplify: false));
    }

    public void ResetBackendState()
    {
        backendMode = false;
        requestInFlight = false;
        lastSimplify = false;
    }

    void OnChoice(string choice)
    {
        // Prototype logic:
        // - understood -> close and spawn enemies
        // - repeat -> backend: call API again (same mode); local: show same text
        // - simplify -> backend: call API with simplify=true; local: show shorter text
        if (requestInFlight) return;
        if (choice == "repeat")
        {
            if (backendMode) StartCoroutine(RequestDialogue(simplify: lastSimplify));
            else if (dialogueText != null) dialogueText.text = lastDialogue;
            return;
        }
        if (choice == "simplify")
        {
            if (backendMode) StartCoroutine(RequestDialogue(simplify: true));
            else
            {
                string simplified = lastDialogue;
                if (simplified.Length > 140) simplified = simplified.Substring(0, 140) + "...";
                if (dialogueText != null) dialogueText.text = simplified;
            }
            return;
        }

        // understood
        Close();
        onUnderstood?.Invoke();

        if (enemyManager == null) enemyManager = FindObjectOfType<EnemyManager>();
        if (enemyManager != null)
        {
            enemyManager.SpawnWave(enemiesToSpawnAfterDialogue);
        }
    }

    public void Close()
    {
        Time.timeScale = 1f;
        requestInFlight = false;
        SetOpen(false);
    }

    void SetOpen(bool open)
    {
        isOpen = open;
        if (panel != null) panel.SetActive(open);
    }

    IEnumerator RequestDialogue(bool simplify)
    {
        if (!backendMode)
        {
            yield break;
        }

        // Show loading state
        requestInFlight = true;
        lastSimplify = simplify;
        SetButtonsInteractable(false);
        if (dialogueText != null) dialogueText.text = "Loading...";

        APIManager api = APIManager.EnsureInstance();
        if (api == null)
        {
            lastDialogue = fallbackDialogue;
            if (dialogueText != null) dialogueText.text = lastDialogue;
            SetButtonsInteractable(true);
            requestInFlight = false;
            yield break;
        }

        bool ok = false;
        string text = "";
        string err = "";

        GameManager gameManager = GameManager.Instance != null ? GameManager.Instance : FindObjectOfType<GameManager>();

        if (gameManager == null || gameManager.GetSessionId() == 0)
        {
            Debug.LogError("[DialogueManager] GenerateDialogue blocked: sessionId == 0.");
            lastDialogue = fallbackDialogue;
            if (dialogueText != null) dialogueText.text = lastDialogue;
            SetButtonsInteractable(true);
            requestInFlight = false;
            yield break;
        }

        yield return api.GenerateDialogue(
            simplify: simplify,
            onOk: (t) => { ok = true; text = t; },
            onErr: (e) => { ok = false; err = e; }
        );

        if (ok && !string.IsNullOrWhiteSpace(text))
        {
            lastDialogue = text.Trim();
        }
        else
        {
            Debug.LogWarning("[DialogueManager] GenerateDialogue failed: " + err);
            lastDialogue = fallbackDialogue;
        }

        if (dialogueText != null) dialogueText.text = lastDialogue;
        SetButtonsInteractable(true);
        requestInFlight = false;
    }

    void SetButtonsInteractable(bool interactable)
    {
        if (understoodButton != null) understoodButton.interactable = interactable;
        if (repeatButton != null) repeatButton.interactable = interactable;
        if (simplifyButton != null) simplifyButton.interactable = interactable;
    }
}
