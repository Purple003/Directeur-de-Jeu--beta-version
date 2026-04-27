using UnityEngine;
using UnityEngine.EventSystems;

public class ButtonEffect : MonoBehaviour, IPointerDownHandler, IPointerUpHandler
{
    public Vector3 normalScale = Vector3.one;
    public Vector3 pressedScale = new Vector3(1.1f, 1.1f, 1.1f);

    public void OnPointerDown(PointerEventData eventData)
    {
        transform.localScale = pressedScale;
    }

    public void OnPointerUp(PointerEventData eventData)
    {
        transform.localScale = normalScale;
    }
}