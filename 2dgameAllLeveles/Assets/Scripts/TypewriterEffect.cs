using System.Collections;
using TMPro;
using UnityEngine;


public class TypewriterEffect : MonoBehaviour
{
    public AudioSource audioSource;
    public AudioClip typingSound;
    public TextMeshProUGUI textComponent;
    public float typingSpeed = 0.03f;

    public void ShowText(string text)
    {
        StopAllCoroutines();
        StartCoroutine(TypeText(text));
    }

    IEnumerator TypeText(string text)
    {
        textComponent.text = "";

        foreach (char c in text)
        {
            textComponent.text += c;

            audioSource.PlayOneShot(typingSound);

            yield return new WaitForSeconds(typingSpeed);
        }
    }
}