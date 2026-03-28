using System.Collections.Generic;
using System.Collections;
using UnityEngine;

public class EnemyManager : MonoBehaviour
{
    [Header("Spawn")]
    public GameObject enemyPrefab;
    public Transform[] spawnPoints;
    public int defaultWaveSize = 5;

    [Header("Optional")]
    public AdaptationManager adaptation;

    private readonly List<GameObject> alive = new List<GameObject>();

    void Awake()
    {
        if (adaptation == null) adaptation = FindObjectOfType<AdaptationManager>();
    }

    public void SpawnWave(int count)
    {
        if (enemyPrefab == null)
        {
            Debug.LogWarning("[EnemyManager] enemyPrefab is null.");
            return;
        }
        if (spawnPoints == null || spawnPoints.Length == 0)
        {
            Debug.LogWarning("[EnemyManager] No spawnPoints set.");
            return;
        }

        int n = Mathf.Max(1, count);

        // Apply adaptation (count & spawn delay) in a simple way.
        float spawnDelay = 0f;
        if (adaptation != null)
        {
            n = adaptation.AdjustEnemyCount(n);
            spawnDelay = adaptation.SpawnDelaySeconds();
        }

        if (spawnDelay > 0.01f)
        {
            StartCoroutine(SpawnWaveWithDelay(n, spawnDelay));
            return;
        }

        for (int i = 0; i < n; i++)
        {
            SpawnOne(i);
        }
    }

    IEnumerator SpawnWaveWithDelay(int count, float delaySeconds)
    {
        int n = Mathf.Max(1, count);
        float d = Mathf.Max(0.01f, delaySeconds);
        for (int i = 0; i < n; i++)
        {
            SpawnOne(i);
            yield return new WaitForSeconds(d);
        }
    }

    void SpawnOne(int i)
    {
        Transform sp = spawnPoints[i % spawnPoints.Length];
        GameObject e = Instantiate(enemyPrefab, sp.position, Quaternion.identity);
        alive.Add(e);

        EnemyAI ai = e.GetComponent<EnemyAI>();
        if (ai != null && adaptation != null) ai.adaptation = adaptation;

        // Ensure a quiz trigger exists on the enemy.
        EnemyQuizTrigger trig = e.GetComponent<EnemyQuizTrigger>();
        if (trig == null) trig = e.AddComponent<EnemyQuizTrigger>();
    }

    public void DestroyEnemy(GameObject enemy)
    {
        if (enemy == null) return;
        alive.Remove(enemy);

        EnemyDeathEffect death = enemy.GetComponent<EnemyDeathEffect>();
        if (death == null) death = enemy.AddComponent<EnemyDeathEffect>();
        death.PlayAndDestroy();
    }

    public void ClearAll()
    {
        for (int i = 0; i < alive.Count; i++)
        {
            if (alive[i] != null) Destroy(alive[i]);
        }
        alive.Clear();
    }
}
