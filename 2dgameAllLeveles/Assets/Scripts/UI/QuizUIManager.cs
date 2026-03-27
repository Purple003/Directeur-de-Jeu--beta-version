using System;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class QuizUIManager : MonoBehaviour
{
    [Header("UI")]
    public GameObject panel;
    public TMP_Text questionText;
    public Button[] answerButtons;
    public TMP_Text feedbackText;
    public TMP_Text timerText;

    [Header("Timer")]
    public float timeLimitSeconds = 10f;

    [Header("Optional")]
    public EmotionCamera emotionCamera;

    private APIManager.GameQuestion current;
    private int currentIndex = -1;
    private Action<bool> onDone;
    private float remaining;
    private float shownAtRealtime;
    private bool isOpen;
    private bool isSubmitting;

    public bool IsOpen => isOpen;

    public void ShowQuiz(APIManager.GameQuestion[] questions, Action<bool> callback)
    {
        // Safety: prevent race conditions / double-open from multiple triggers in the same frame.
        if (isOpen)
        {
            Debug.LogWarning("[QuizUI] ShowQuiz blocked: already open.");
            return;
        }

        onDone = callback;
        if (panel != null) panel.SetActive(true);
        if (feedbackText != null) feedbackText.text = "";
        isOpen = true;
        isSubmitting = false;

        if (questions == null || questions.Length == 0)
        {
            if (questionText != null) questionText.text = "No questions available.";
            return;
        }

        currentIndex = UnityEngine.Random.Range(0, questions.Length);
        current = questions[currentIndex];
        remaining = Mathf.Max(1f, timeLimitSeconds);
        shownAtRealtime = Time.realtimeSinceStartup;
        RenderCurrent();
        Time.timeScale = 0f;
    }

    void Update()
    {
        if (!isOpen) return;
        if (remaining <= 0f) return;

        remaining -= Time.unscaledDeltaTime;
        if (timerText != null) timerText.text = Mathf.CeilToInt(Mathf.Max(0f, remaining)).ToString();

        if (remaining <= 0f)
        {
            if (feedbackText != null) feedbackText.text = "Time's up!";
            Close(false);
        }
    }

    void RenderCurrent()
    {
        if (questionText != null) questionText.text = current.question;
        if (timerText != null) timerText.text = Mathf.CeilToInt(Mathf.Max(0f, remaining)).ToString();

        if (emotionCamera == null) emotionCamera = FindObjectOfType<EmotionCamera>();
        if (emotionCamera != null) emotionCamera.SetQuestionContext(current.id);

        for (int i = 0; i < answerButtons.Length; i++)
        {
            int idx = i;
            if (answerButtons[i] == null) continue;
            var txt = answerButtons[i].GetComponentInChildren<TMP_Text>();
            bool has = current.choices != null && idx < current.choices.Length;
            if (txt != null) txt.text = has ? current.choices[idx] : "";
            answerButtons[i].interactable = has;
            answerButtons[i].onClick.RemoveAllListeners();
            if (has) answerButtons[i].onClick.AddListener(() => Select(idx));
        }
    }

    void Select(int idx)
    {
        if (!isOpen) return;
        if (isSubmitting) return;

        if (current == null || current.id <= 0)
        {
            Debug.LogWarning("[QuizUI] SubmitAnswer blocked: current question is missing/invalid.");
            Close(false);
            return;
        }

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st == null || st.sessionId <= 0)
        {
            Debug.LogWarning("[QuizUI] SubmitAnswer blocked: session is not initialized (sessionId <= 0).");
            Close(false);
            return;
        }

        // Prevent double-click racing (can send duplicate answers).
        isSubmitting = true;
        SetButtonsInteractable(false);

        string selectedLetter = ((char)('A' + idx)).ToString();
        int timeSpentMs = Mathf.Max(0, Mathf.RoundToInt((Time.realtimeSinceStartup - shownAtRealtime) * 1000f));
        string em = (emotionCamera != null) ? (emotionCamera.lastEmotion ?? "") : "";
        float conf = (emotionCamera != null) ? emotionCamera.lastConfidence : 0.0f;

        Debug.Log($"[QuizUI] SubmitAnswer questionId={current.id} selected={selectedLetter} timeMs={timeSpentMs} emotion={em} conf={conf:0.00}");

        StartCoroutine(APIManager.Instance.SubmitAnswerForCurrentSession(
            questionId: current.id,
            selectedAnswer: selectedLetter,
            timeSpentMs: timeSpentMs,
            emotion: em,
            confidence: conf,
            (isCorrect) =>
            {
                if (feedbackText != null) feedbackText.text = isCorrect ? "Correct!" : "Wrong!";
                Close(isCorrect);
            },
            (err) =>
            {
                Debug.LogWarning("[QuizUI] SubmitAnswer error: " + err);
                Close(false);
            }
        ));
    }

    void Close(bool correct)
    {
        if (!isOpen) return;

        Time.timeScale = 1f;
        isOpen = false;
        isSubmitting = false;
        SetButtonsInteractable(true);
        if (panel != null) panel.SetActive(false);
        onDone?.Invoke(correct);
        onDone = null;
    }

    void SetButtonsInteractable(bool enabled)
    {
        if (answerButtons == null) return;
        for (int i = 0; i < answerButtons.Length; i++)
        {
            if (answerButtons[i] != null) answerButtons[i].interactable = enabled;
        }
    }
}
