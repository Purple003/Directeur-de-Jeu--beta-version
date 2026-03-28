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

    [Header("Follow")]
    public bool enableFollow = true;
    public float followDistance = 5f;
    public float stopDistance = 0.8f;
    public Transform player;

    [Header("Adaptation (Optional)")]
    public AdaptationManager adaptation;
    public bool useAdaptationSpeed = true;

    [Header("Damage")]
    public int damage = 1;

    private Rigidbody2D rb;
    private bool goingRight = true;
    private float baseSpeed;

    void Awake()
    {
        rb = GetComponent<Rigidbody2D>();
        baseSpeed = speed;
        if (type == EnemyType.Bat)
        {
            rb.gravityScale = 0f;
        }

        if (player == null)
        {
            GameObject p = GameObject.FindGameObjectWithTag("Player");
            if (p != null) player = p.transform;
        }
        if (adaptation == null) adaptation = FindObjectOfType<AdaptationManager>();
    }

    void FixedUpdate()
    {
        if (player == null)
        {
            GameObject p = GameObject.FindGameObjectWithTag("Player");
            if (p != null) player = p.transform;
        }

        float currentSpeed = baseSpeed;
        if (useAdaptationSpeed && adaptation != null) currentSpeed *= adaptation.EnemySpeedMultiplier();

        if (enableFollow && player != null && followDistance > 0f)
        {
            float d = Vector2.Distance(transform.position, player.position);
            if (d <= followDistance)
            {
                FollowPlayer(currentSpeed, d);
                return;
            }
        }

        Patrol(currentSpeed);
    }

    void FollowPlayer(float currentSpeed, float distanceToPlayer)
    {
        Vector2 delta = (Vector2)(player.position - transform.position);
        if (distanceToPlayer <= Mathf.Max(0.05f, stopDistance))
        {
            // Stop horizontally when close to the player (keeps y velocity for jumps/falls).
            rb.velocity = new Vector2(0f, rb.velocity.y);
            return;
        }

        if (type == EnemyType.Bat)
        {
            Vector2 dir = delta.normalized;
            rb.velocity = dir * currentSpeed;
            FlipByX(dir.x);
            return;
        }

        // Slime: follow only on X (ground enemy).
        float xDir = Mathf.Sign(delta.x);
        rb.velocity = new Vector2(xDir * currentSpeed, rb.velocity.y);
        FlipByX(xDir);
    }

    void Patrol(float currentSpeed)
    {
        if (leftPoint == null || rightPoint == null) return;

        float dir = goingRight ? 1f : -1f;
        rb.velocity = new Vector2(dir * currentSpeed, rb.velocity.y);

        if (goingRight && transform.position.x >= rightPoint.position.x) goingRight = false;
        if (!goingRight && transform.position.x <= leftPoint.position.x) goingRight = true;

        FlipByX(goingRight ? 1f : -1f);
    }

    void FlipByX(float xDir)
    {
        if (xDir == 0f) return;
        Vector3 s = transform.localScale;
        s.x = xDir > 0f ? Mathf.Abs(s.x) : -Mathf.Abs(s.x);
        transform.localScale = s;
    }

    void OnCollisionEnter2D(Collision2D collision)
    {
        // Damage is applied by GameManager when the player answers the quiz incorrectly.
        // Collision here is used only to open a quiz (see EnemyQuizTrigger).
    }
}
