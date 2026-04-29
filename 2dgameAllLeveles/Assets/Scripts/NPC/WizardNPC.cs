using UnityEngine;

[RequireComponent(typeof(Collider2D))]
public class WizardNPC : MonoBehaviour
{
    [Header("Dialogue")]
    [TextArea(3, 8)]
    public string dialogueText = "Hello! I will explain the concept. If you understood, we can start the quiz enemies.";

    public KeyCode interactKey = KeyCode.E;

    [Header("References")]
    public DialogueManager dialogueManager;

    private bool playerInRange = false;
    private bool triggeredOnce = false;

    void Reset()
    {
        // Make sure this collider is a trigger (NPC interaction zone)
        Collider2D c = GetComponent<Collider2D>();
        if (c != null) c.isTrigger = true;
    }

    void Update()
    {
        if (!playerInRange) return;
        if (triggeredOnce) return;
        if (Input.GetKeyDown(interactKey))
        {
            if (dialogueManager == null) dialogueManager = FindObjectOfType<DialogueManager>();
            if (dialogueManager == null) return;

            GameManager gameManager = GameManager.Instance != null ? GameManager.Instance : FindObjectOfType<GameManager>();
        
            if (gameManager == null || gameManager.GetSessionId() <= 0 || gameManager.CourseId <= 0)
            {
                // Session might still be bootstrapping; allow the player to retry.
                dialogueManager.ShowDialogue("Loading session... please wait and press E again.");
                return;
            }

            triggeredOnce = true;
            dialogueManager.ShowBackendDialogue(dialogueText);
        }
    }

    void OnTriggerEnter2D(Collider2D other)
    {
        if (other.CompareTag("Player")) playerInRange = true;
    }

    void OnTriggerExit2D(Collider2D other)
    {
        if (other.CompareTag("Player")) playerInRange = false;
    }
}
