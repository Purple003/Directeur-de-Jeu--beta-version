using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class UIMusicToggle : MonoBehaviour
{
    [Header("Images")]
    public Sprite musicOnSprite;
    public Sprite musicOffSprite;

    private Image buttonImage;
    private bool isMuted = false;

    void Start()
    {
        buttonImage = GetComponent<Image>();
        UpdateIcon();
    }

    public void ToggleMusic()
    {
        if (AudioManager.Instance != null)
        {
            AudioManager.Instance.ToggleMute();
            isMuted = AudioManager.Instance.IsMuted();
            UpdateIcon();
        }
    }

    void UpdateIcon()
    {
        if (buttonImage != null)
        {
            buttonImage.sprite = isMuted ? musicOffSprite : musicOnSprite;
        }
    }
}
