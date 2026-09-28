import sqlite3
import os

DATABASE = 'database/event_organizer.db'
SCHEMA = 'database/schema.sql'

def init():
    if os.path.exists(DATABASE):
        os.remove(DATABASE)
        print("Deleted existing DB")
    
    db = sqlite3.connect(DATABASE)
    with open(SCHEMA, 'r') as f:
        schema = f.read()
    
    # Apply the same logic as app.py
    schema = schema.replace('INT AUTO_INCREMENT PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
    schema = schema.replace('ENUM(\'admin\', \'user\') DEFAULT \'user\'', 'TEXT DEFAULT \'user\'')
    schema = schema.replace('ENUM(\'pending\', \'confirmed\', \'cancelled\') DEFAULT \'pending\'', 'TEXT DEFAULT \'pending\'')
    schema = schema.replace('ENUM(\'unpaid\', \'paid\', \'refunded\') DEFAULT \'unpaid\'', 'TEXT DEFAULT \'unpaid\'')
    schema = schema.replace('ENUM(\'success\', \'failed\', \'pending\') DEFAULT \'pending\'', 'TEXT DEFAULT \'pending\'')
    schema = schema.replace('BOOLEAN DEFAULT FALSE', 'INTEGER DEFAULT 0')
    schema = schema.replace('BOOLEAN DEFAULT TRUE', 'INTEGER DEFAULT 1')
    schema = schema.replace('TIMESTAMP DEFAULT CURRENT_TIMESTAMP', 'DATETIME DEFAULT CURRENT_TIMESTAMP')
    
    try:
        db.executescript(schema)
        db.commit()
        print("Schema applied successfully!")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    init()
