using UnityEngine;

public class CameraFollow2D : MonoBehaviour
{
    public Transform target;
    public Vector3 offset = new Vector3(0f, 1.2f, -10f);
    public float smoothTime = 0.18f;
    public bool lockY = false;

    private Vector3 velocity;

    void LateUpdate()
    {
        if (target == null)
        {
            GameObject p = GameObject.FindGameObjectWithTag("Player");
            if (p != null) target = p.transform;
            else return;
        }

        Vector3 desired = target.position + offset;
        if (lockY) desired.y = transform.position.y;

        // Keep camera Z stable for 2D.
        desired.z = offset.z;

        transform.position = Vector3.SmoothDamp(transform.position, desired, ref velocity, Mathf.Max(0.01f, smoothTime));
    }
}

