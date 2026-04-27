import psycopg2

conn = psycopg2.connect(
    host='localhost', port=5432,
    dbname='adaptive_game_db',
    user='adaptive_user',
    password='1234'
)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM questions WHERE course_id = 53")
total = cur.fetchone()[0]
print(f"TOTAL COUNT: {total}")

cur.execute(
    "SELECT difficulty_level, COUNT(*) FROM questions WHERE course_id = 53 GROUP BY difficulty_level ORDER BY difficulty_level"
)
rows = cur.fetchall()
print("Repartition par difficulty_level:")
for r in rows:
    print(f"  {r[0]}: {r[1]}")

conn.close()
