from db import get_db_connection

conn = None
try:
    conn = get_db_connection()

    if conn.is_connected():
        print("✅ MySQL Connected Successfully")

except Exception as e:
    print("❌ Error:", e)

finally:
    try:
        if conn and conn.is_connected():
            conn.close()
    except Exception:
        pass
