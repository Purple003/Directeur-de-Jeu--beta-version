using UnityEngine;

[RequireComponent(typeof(Collider2D))]
public class EnemyQuizTrigger : MonoBehaviour
{
    private bool inQuiz = false;
    private Collider2D col;

    void Awake()
    {
        col = GetComponent<Collider2D>();
    }

    void OnCollisionEnter2D(Collision2D collision)
    {
        if (inQuiz) return;
        if (!collision.collider.CompareTag("Player")) return;

        GameManager gm = FindObjectOfType<GameManager>();
        if (gm == null) return;

        if (!gm.IsReadyForQuiz()) return;

        FindObjectOfType<EmotionCamera>()?.AnalyzeNow(0);

        inQuiz = true;
        // IMPORTANT: keep the collider enabled here. The quiz flow performs an
        // async backend call (GetNextQuestion). If we disable the collider now
        // the enemy will lose ground contact and fall while waiting for the
        // question. The collider will be disabled only once the UI is shown
        // (see GameManager.OpenNextQuestionQuiz where pendingEnemy collider is
        // disabled immediately after QuizUIManager.ShowQuiz returns).

        gm.TriggerQuizForEnemy(gameObject, () =>
        {
            // Re-enable collision if enemy still exists and wasn't destroyed.
            inQuiz = false;
            if (col != null)
            {
                EnemyDeathEffect death = GetComponent<EnemyDeathEffect>();
                if (death != null && death.IsDying) return;
                col.enabled = true;
            }
        });
    }
}
