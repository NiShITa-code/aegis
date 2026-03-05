import sqlite3
import sys

def init_db():
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)')
    cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'supersecret', 'admin')")
    cursor.execute("INSERT INTO users (username, password, role) VALUES ('user1', 'pass1', 'user')")
    conn.commit()
    return conn

def authenticate(conn, username, password):
    # VULNERABLE: Classic SQL Injection
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    print(f"Executing: {query}")
    try:
        cursor.execute(query)
        user = cursor.fetchone()
        if user:
            print(f"Authenticated as {user[1]} with role {user[3]}")
            return True
        else:
            print("Authentication failed.")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python vuln_app.py <username> <password>")
        sys.exit(1)
    
    conn = init_db()
    authenticate(conn, sys.argv[1], sys.argv[2])
