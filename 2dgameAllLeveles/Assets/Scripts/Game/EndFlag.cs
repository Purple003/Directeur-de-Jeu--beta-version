using UnityEngine;

// Put this on the level end trigger object (with a 2D trigger collider).
public class EndFlag : MonoBehaviour
{
    void OnTriggerEnter2D(Collider2D other)
    {
        if (!other.CompareTag("Player")) return;
        GameManager gm = FindObjectOfType<GameManager>();
        if (gm != null) gm.CompleteLevel();
    }
}

