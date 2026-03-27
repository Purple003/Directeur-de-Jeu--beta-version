using UnityEngine;

public class Coin : MonoBehaviour
{
    public int xpValue = 5;

    void OnTriggerEnter2D(Collider2D other)
    {
        if (!other.CompareTag("Player")) return;

        GameManager gm = FindObjectOfType<GameManager>();
        if (gm != null) gm.AddXP(xpValue);

        PlayerSessionState st = PlayerSessionState.EnsureInstance();
        if (st != null && APIManager.EnsureInstance() != null && st.playerId > 0)
        {
            StartCoroutine(APIManager.Instance.UpdateProgress(
                st.playerId,
                xpValue,
                0,
                (resp) =>
                {
                    st.xp = resp.xp;
                    st.stars = resp.stars;
                    st.gameLevel = resp.game_level;
                },
                (err) => Debug.LogWarning("[API] UpdateProgress failed: " + err)
            ));
        }

        Destroy(gameObject);
    }
}
