using UnityEngine;

[RequireComponent(typeof(Rigidbody2D))]
public class EnemyAI : MonoBehaviour
{
    public enum EnemyType { Slime, Bat }
    public EnemyType type = EnemyType.Slime;

    [Header("Patrol")]
    public float speed = 2f;
    public Transform leftPoint;
    public Transform rightPoint;

    [Header("Damage")]
    public int damage = 1;

    private Rigidbody2D rb;
    private bool goingRight = true;

    void Awake()
    {
        rb = GetComponent<Rigidbody2D>();
        if (type == EnemyType.Bat)
        {
            rb.gravityScale = 0f;
        }
    }

    void FixedUpdate()
    {
        if (leftPoint == null || rightPoint == null) return;

        float dir = goingRight ? 1f : -1f;
        rb.velocity = new Vector2(dir * speed, rb.velocity.y);

        if (goingRight && transform.position.x >= rightPoint.position.x) goingRight = false;
        if (!goingRight && transform.position.x <= leftPoint.position.x) goingRight = true;

        Vector3 s = transform.localScale;
        s.x = goingRight ? Mathf.Abs(s.x) : -Mathf.Abs(s.x);
        transform.localScale = s;
    }

    void OnCollisionEnter2D(Collision2D collision)
    {
        if (!collision.collider.CompareTag("Player")) return;
        GameManager gm = FindObjectOfType<GameManager>();
        if (gm != null) gm.TakeDamage(damage);
    }
}

