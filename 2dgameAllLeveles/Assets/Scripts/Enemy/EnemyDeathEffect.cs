using System.Collections;
using UnityEngine;

public class EnemyDeathEffect : MonoBehaviour
{
    [Header("Effect")]
    public float fadeDuration = 0.25f;
    public float shrinkMultiplier = 0.9f;
    public float riseDistance = 0.15f;

    public bool IsDying => isDying;

    private bool isDying = false;
    private SpriteRenderer sr;
    private Rigidbody2D rb;
    private Collider2D col;

    void Awake()
    {
        sr = GetComponentInChildren<SpriteRenderer>();
        rb = GetComponent<Rigidbody2D>();
        col = GetComponent<Collider2D>();
    }

    public void PlayAndDestroy()
    {
        if (isDying) return;
        isDying = true;

        // Prevent further interactions.
        if (col != null) col.enabled = false;
        if (rb != null) rb.simulated = false;

        EnemyAI ai = GetComponent<EnemyAI>();
        if (ai != null) ai.enabled = false;

        EnemyQuizTrigger trig = GetComponent<EnemyQuizTrigger>();
        if (trig != null) trig.enabled = false;

        StartCoroutine(FadeAndDestroy());
    }

    IEnumerator FadeAndDestroy()
    {
        float d = Mathf.Max(0.01f, fadeDuration);
        float t = 0f;
        Vector3 startPos = transform.position;
        Vector3 endPos = startPos + new Vector3(0f, riseDistance, 0f);
        Vector3 startScale = transform.localScale;
        Vector3 endScale = startScale * Mathf.Max(0.01f, shrinkMultiplier);

        Color c0 = sr != null ? sr.color : Color.white;
        while (t < d)
        {
            t += Time.deltaTime;
            float a = Mathf.Clamp01(t / d);

            transform.position = Vector3.Lerp(startPos, endPos, a);
            transform.localScale = Vector3.Lerp(startScale, endScale, a);

            if (sr != null)
            {
                Color c = c0;
                c.a = Mathf.Lerp(c0.a, 0f, a);
                sr.color = c;
            }

            yield return null;
        }

        Destroy(gameObject);
    }
}

