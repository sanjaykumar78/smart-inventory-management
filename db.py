import mysql.connector

print("LOADING DB.PY")

def get_db_connection():
    return mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="Sanjay@191",
        database="smart_inventory"
    )