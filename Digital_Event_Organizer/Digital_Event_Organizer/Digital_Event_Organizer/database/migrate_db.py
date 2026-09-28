import sqlite3
import os
import sys
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.ticket_service import generate_ticket_code, generate_qr_image

DATABASE = os.path.join(os.path.dirname(__file__), 'event_organizer.db')

def migrate():
    print(f"Migrating database: {DATABASE}")
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. First, check and add missing columns to users
    cursor.execute("PRAGMA table_info(users)")
    user_cols = [row['name'] for row in cursor.fetchall()]
    if 'is_active' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
        print("Added is_active column to users")

    # Update role 'user' to 'attendee'
    cursor.execute("UPDATE users SET role = 'attendee' WHERE role = 'user'")
    conn.commit()

    # 2. Check and add missing columns to events
    cursor.execute("PRAGMA table_info(events)")
    event_cols = [row['name'] for row in cursor.fetchall()]
    missing_event_cols = {
        'organizer_id': 'INTEGER DEFAULT 1',
        'end_time': 'TIME',
        'address': 'VARCHAR(255)',
        'city': 'VARCHAR(100)',
        'contact_email': 'VARCHAR(100)',
        'contact_phone': 'VARCHAR(20)',
        'requirements': 'TEXT',
        'tags': 'VARCHAR(255)',
        'status': "VARCHAR(30) DEFAULT 'PUBLISHED'",
        'rejection_reason': 'TEXT'
    }
    for col, col_type in missing_event_cols.items():
        if col not in event_cols:
            cursor.execute(f"ALTER TABLE events ADD COLUMN {col} {col_type}")
            print(f"Added {col} column to events")

    # Update any NULL status to PUBLISHED for existing events
    cursor.execute("UPDATE events SET status = 'PUBLISHED' WHERE status IS NULL OR status = ''")
    conn.commit()

    # 3. Check and add missing columns to registrations
    cursor.execute("PRAGMA table_info(registrations)")
    reg_cols = [row['name'] for row in cursor.fetchall()]
    if 'ticket_code' not in reg_cols:
        cursor.execute("ALTER TABLE registrations ADD COLUMN ticket_code VARCHAR(50)")
        print("Added ticket_code column to registrations")
    if 'checked_in_at' not in reg_cols:
        cursor.execute("ALTER TABLE registrations ADD COLUMN checked_in_at DATETIME")
        print("Added checked_in_at column to registrations")
    conn.commit()

    # 4. Check and add missing columns to notifications
    cursor.execute("PRAGMA table_info(notifications)")
    notif_cols = [row['name'] for row in cursor.fetchall()]
    if 'title' not in notif_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN title VARCHAR(150)")
        print("Added title column to notifications")
    if 'type' not in notif_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN type VARCHAR(20) DEFAULT 'info'")
        print("Added type column to notifications")
    if 'link' not in notif_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN link VARCHAR(255)")
        print("Added link column to notifications")
    conn.commit()

    # 5. Now execute schema script to create categories, tickets, reviews, payments tables and indexes
    with open(os.path.join(os.path.dirname(__file__), 'schema.sql'), 'r') as f:
        schema_sql = f.read()
    cursor.executescript(schema_sql)
    conn.commit()

    # Ensure organizer user exists
    cursor.execute("SELECT * FROM users WHERE email = 'organizer@event.com'")
    organizer = cursor.fetchone()
    if not organizer:
        org_hash = generate_password_hash('organizer123')
        cursor.execute("INSERT INTO users (name, email, password, role, is_active) VALUES (?, ?, ?, ?, 1)",
                       ('Prof. Ramesh Organizer', 'organizer@event.com', org_hash, 'organizer'))
        conn.commit()
        print("Created organizer account: organizer@event.com")
        cursor.execute("SELECT * FROM users WHERE email = 'organizer@event.com'")
        organizer = cursor.fetchone()

    # Ensure admin user exists
    cursor.execute("SELECT * FROM users WHERE email = 'admin@event.com'")
    admin = cursor.fetchone()
    if not admin:
        admin_hash = generate_password_hash('admin123')
        cursor.execute("INSERT INTO users (name, email, password, role, is_active) VALUES (?, ?, ?, ?, 1)",
                       ('System Administrator', 'admin@event.com', admin_hash, 'admin'))
        conn.commit()
        print("Created admin account: admin@event.com")

    # Update organizer_id on events if null or 0
    if organizer:
        cursor.execute("UPDATE events SET organizer_id = ? WHERE organizer_id IS NULL OR organizer_id = 0", (organizer['user_id'],))
        conn.commit()

    # 6. Seed default categories
    categories = [
        ('Tech', 'Coding, Hackathons, AI, and Software symposiums', 'fa-laptop-code'),
        ('Workshop', 'Hands-on training, bootcamps, and technical skills', 'fa-tools'),
        ('Cultural', 'Music, dance, art, drama, and entertainment festivals', 'fa-music'),
        ('Seminar', 'Keynotes, expert talks, and academic lectures', 'fa-chalkboard-teacher'),
        ('Sports', 'Athletics, tournaments, indoor and outdoor games', 'fa-running'),
        ('Business', 'Entrepreneurship, startup pitch decks, and finance summits', 'fa-briefcase')
    ]
    for cat_name, desc, icon in categories:
        cursor.execute("SELECT * FROM categories WHERE name = ?", (cat_name,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO categories (name, description, icon) VALUES (?, ?, ?)",
                           (cat_name, desc, icon))
            print(f"Seeded category: {cat_name}")
    conn.commit()

    # 7. Ensure tickets exist for existing confirmed registrations
    cursor.execute("SELECT * FROM registrations WHERE status = 'confirmed'")
    confirmed_regs = cursor.fetchall()
    for reg in confirmed_regs:
        reg_id = reg['registration_id']
        cursor.execute("SELECT * FROM tickets WHERE registration_id = ?", (reg_id,))
        ticket = cursor.fetchone()
        if not ticket:
            ticket_code = reg['ticket_code'] or generate_ticket_code(reg['event_id'], reg['user_id'])
            qr_data, qr_uri, qr_path = generate_qr_image(ticket_code, reg['event_id'], reg['user_id'])
            cursor.execute("UPDATE registrations SET ticket_code = ? WHERE registration_id = ?", (ticket_code, reg_id))
            cursor.execute('''
                INSERT INTO tickets (registration_id, ticket_code, event_id, user_id, qr_data, qr_path, status)
                VALUES (?, ?, ?, ?, ?, ?, 'VALID')
            ''', (reg_id, ticket_code, reg['event_id'], reg['user_id'], qr_data, qr_path))
            print(f"Generated ticket {ticket_code} for registration {reg_id}")
    conn.commit()

    conn.close()
    print("Migration completed successfully!")

if __name__ == '__main__':
    migrate()
