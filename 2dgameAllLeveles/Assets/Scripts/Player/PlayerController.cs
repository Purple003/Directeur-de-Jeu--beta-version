using UnityEngine;

[RequireComponent(typeof(Rigidbody2D))]
public class PlayerController : MonoBehaviour
{
    [Header("Move")]
    public float moveSpeed = 6f;
    public float jumpForce = 12f;
    public int maxJumps = 2;

    [Header("Game Feel")]
    public bool enableJumpSquash = true;
    public Vector2 jumpSquashScale = new Vector2(1.08f, 0.92f);
    public float jumpSquashDuration = 0.08f;
    public float jumpReturnDuration = 0.10f;

    [Header("Ground Check")]
    public Transform groundCheck;
    public float groundCheckRadius = 0.12f;
    public LayerMask groundLayer;

    private Rigidbody2D rb;
    private int jumpsLeft;
    private bool isGrounded;
    private Vector3 baseScale;
    private Coroutine jumpSquashRoutine;

    void Awake()
    {
        rb = GetComponent<Rigidbody2D>();
        baseScale = transform.localScale;
    }

    void Start()
    {
        jumpsLeft = maxJumps;
    }

    void Update()
    {
        float x = Input.GetAxisRaw("Horizontal");
        rb.velocity = new Vector2(x * moveSpeed, rb.velocity.y);

        if (x != 0)
        {
            Vector3 s = transform.localScale;
            s.x = Mathf.Sign(x) * Mathf.Abs(s.x);
            transform.localScale = s;
        }

        if (Input.GetButtonDown("Jump") && jumpsLeft > 0)
        {
            rb.velocity = new Vector2(rb.velocity.x, 0f);
            rb.AddForce(Vector2.up * jumpForce, ForceMode2D.Impulse);
            jumpsLeft--;
            if (enableJumpSquash) KickJumpSquash();
        }
    }

    void FixedUpdate()
    {
        if (groundCheck != null)
        {
            isGrounded = Physics2D.OverlapCircle(groundCheck.position, groundCheckRadius, groundLayer);
            if (isGrounded)
            {
                jumpsLeft = maxJumps;
            }
        }
    }

    void KickJumpSquash()
    {
        if (jumpSquashRoutine != null) StopCoroutine(jumpSquashRoutine);
        jumpSquashRoutine = StartCoroutine(JumpSquash());
    }

    System.Collections.IEnumerator JumpSquash()
    {
        Vector3 squash = new Vector3(baseScale.x * jumpSquashScale.x, baseScale.y * jumpSquashScale.y, baseScale.z);

        float t = 0f;
        float d1 = Mathf.Max(0.01f, jumpSquashDuration);
        while (t < d1)
        {
            t += Time.deltaTime;
            float a = Mathf.Clamp01(t / d1);
            transform.localScale = Vector3.Lerp(baseScale, squash, a);
            yield return null;
        }

        t = 0f;
        float d2 = Mathf.Max(0.01f, jumpReturnDuration);
        while (t < d2)
        {
            t += Time.deltaTime;
            float a = Mathf.Clamp01(t / d2);
            transform.localScale = Vector3.Lerp(squash, baseScale, a);
            yield return null;
        }

        transform.localScale = baseScale;
        jumpSquashRoutine = null;
    }
}
