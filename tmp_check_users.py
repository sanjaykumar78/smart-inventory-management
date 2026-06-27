import mysql.connector

conn = mysql.connector.connect(host='127.0.0.1', user='root', password='Sanjay@191', database='smart_inventory')
cur = conn.cursor(dictionary=True)
cur.execute('SELECT username, role FROM users')
print(cur.fetchall())
conn.close()
