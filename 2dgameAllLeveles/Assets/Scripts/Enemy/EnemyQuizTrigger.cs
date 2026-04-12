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

        FindObjectOfType<EmotionCamera>()?.AnalyzeNow(PlayerSessionState.EnsureInstance().sessionId, 0);

        inQuiz = true;
        if (col != null) col.enabled = false; // avoid retrigger while quiz is open

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
