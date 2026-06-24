import json
import os
from db import get_db_connection

USERS_PATH = "users.json"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) UNIQUE,
    full_name VARCHAR(255),
    email VARCHAR(255),
    password TEXT,
    theme VARCHAR(50),
    profile_picture VARCHAR(255)
)
"""


def load_users_file(path):
    if not os.path.exists(path):
        print(f"users file not found at '{path}'")
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print("Failed to read users.json:", e)
        return {}


def migrate():
    users = load_users_file(USERS_PATH)
    if not users:
        print("No users to migrate.")
        return

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Ensure table exists
        cursor.execute(CREATE_TABLE_SQL)
        conn.commit()

        for username, record in users.items():
            # check if exists
            cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
            existing = cursor.fetchone()
            if existing:
                print(f"Skipped: {username}")
                continue

            # map JSON field 'password_hash' into DB 'password' column
            password = record.get('password_hash')
            profile_picture = record.get('profile_picture')
            full_name = record.get('full_name')
            email = record.get('email')
            theme = record.get('theme')

            insert_sql = """
            INSERT INTO users (
                username,
                full_name,
                email,
                password,
                theme,
                profile_picture
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (username, full_name, email, password, theme, profile_picture))
            conn.commit()
            print(f"Migrated: {username}")

    except Exception as e:
        print("Error during migration:", e)
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    migrate()
