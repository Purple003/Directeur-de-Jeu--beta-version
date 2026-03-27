using UnityEngine;

public class QuizTrigger : MonoBehaviour
{
    public bool oneShot = true;
    private bool used = false;

    void OnTriggerEnter2D(Collider2D other)
    {
        if (!other.CompareTag("Player")) return;

        GameManager gm = FindObjectOfType<GameManager>();
        if (gm == null) return;
        if (!gm.IsReadyForQuiz())
        {
            Debug.LogWarning("[Game] QuizTrigger blocked: game not ready (session/questions not initialized).");
            return;
        }

        if (oneShot && used) return;
        used = true;
        gm.TriggerQuiz();
    }
}
