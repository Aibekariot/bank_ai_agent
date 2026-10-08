from database import get_connection


with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        version = cur.fetchone()

        print("Подключение успешно!")
        print(version[0])