import sqlite3
import os

DATABASE = os.path.join(os.getcwd(), 'database', 'event_organizer.db')

if not os.path.exists(DATABASE):
    print("Database file NOT FOUND")
else:
    db = sqlite3.connect(DATABASE)
    cursor = db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables found: {[t[0] for t in tables]}")
    db.close()
