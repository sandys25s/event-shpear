import sqlite3
import os
import sys
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'event_organizer.db')
if not os.path.exists(DATABASE):
    DATABASE = 'database/event_organizer.db'

def seed():
    if not os.path.exists(DATABASE):
        print("Database not found. Initializing...")
        import database.migrate_db as mig
        mig.migrate()
    
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()
    
    # 1. Create Users for all 3 roles
    admin_pass = generate_password_hash('admin123')
    org_pass = generate_password_hash('organizer123')
    user_pass = generate_password_hash('user123')
    
    users = [
        ('Admin User', 'admin@event.com', admin_pass, 'admin', 1),
        ('Prof. Ramesh Organizer', 'organizer@event.com', org_pass, 'organizer', 1),
        ('Santhosh Kumar', 'user@event.com', user_pass, 'attendee', 1),
        ('Priya Sharma', 'attendee@event.com', user_pass, 'attendee', 1)
    ]
    
    for u in users:
        cursor.execute("SELECT * FROM users WHERE email = ?", (u[1],))
        existing = cursor.fetchone()
        if not existing:
            cursor.execute("INSERT INTO users (name, email, password, role, is_active) VALUES (?, ?, ?, ?, ?)", u)
            print(f"Added user: {u[1]} ({u[3]})")
        else:
            # ensure role is correct
            cursor.execute("UPDATE users SET role = ?, is_active = 1 WHERE email = ?", (u[3], u[1]))

    cursor.execute("SELECT user_id FROM users WHERE email = 'organizer@event.com'")
    org_row = cursor.fetchone()
    org_id = org_row['user_id'] if org_row else 1

    # 2. Categories
    categories = [
        ('Tech', 'Coding, Hackathons, AI, and Software symposiums', 'fa-laptop-code'),
        ('Workshop', 'Hands-on training, bootcamps, and technical skills', 'fa-tools'),
        ('Cultural', 'Music, dance, art, drama, and entertainment festivals', 'fa-music'),
        ('Seminar', 'Keynotes, expert talks, and academic lectures', 'fa-chalkboard-teacher'),
        ('Sports', 'Athletics, tournaments, indoor and outdoor games', 'fa-running'),
        ('Business', 'Entrepreneurship, startup pitch decks, and finance summits', 'fa-briefcase')
    ]
    for c in categories:
        cursor.execute("SELECT * FROM categories WHERE name = ?", (c[0],))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO categories (name, description, icon) VALUES (?, ?, ?)", c)

    # 3. Dynamic Future Dates
    today = datetime.now().date()
    d1 = (today + timedelta(days=10)).strftime('%Y-%m-%d')
    d2 = (today + timedelta(days=18)).strftime('%Y-%m-%d')
    d3 = (today + timedelta(days=25)).strftime('%Y-%m-%d')
    d4 = (today + timedelta(days=32)).strftime('%Y-%m-%d')
    d5 = (today - timedelta(days=15)).strftime('%Y-%m-%d') # Completed event

    dl1 = (today + timedelta(days=9)).strftime('%Y-%m-%d 23:59:00')
    dl2 = (today + timedelta(days=17)).strftime('%Y-%m-%d 23:59:00')
    dl3 = (today + timedelta(days=24)).strftime('%Y-%m-%d 23:59:00')
    dl4 = (today + timedelta(days=31)).strftime('%Y-%m-%d 23:59:00')
    dl5 = (today - timedelta(days=16)).strftime('%Y-%m-%d 23:59:00')

    events = [
        (
            org_id,
            'Annual Tech Symposium 2026', 
            'State-level technology festival featuring 24-hr hackathons, tech talks from FAANG leaders, and project exhibitions with cash prizes.',
            d1, '09:00', '17:00', 'Main Auditorium', 'Campus Central Avenue', 'Chennai',
            'Tech', 350.00, 1, 150, 42, dl1,
            'https://images.unsplash.com/photo-1540575861501-7ad0582373f2?auto=format&fit=crop&q=80&w=800',
            'techfest@eventorg.com', '+91 98765 43210', 'Laptop required with Python/Node environment',
            'tech, hackathon, coding, ai', 'PUBLISHED', None
        ),
        (
            org_id,
            'Hands-on AI & Deep Learning Masterclass', 
            'Comprehensive practical workshop covering LLMs, neural networks, PyTorch, and deploying models to cloud.',
            d2, '10:00', '16:00', 'Seminar Hall B', 'Academic Block 3', 'Bengaluru',
            'Workshop', 199.00, 1, 60, 58, dl2,
            'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&q=80&w=800',
            'ai-workshop@eventorg.com', '+91 98765 43211', 'Basic Python knowledge recommended',
            'ai, deeplearning, workshop, pytorch', 'PUBLISHED', None
        ),
        (
            org_id,
            'Campus Cultural Fest: Rhythm 2026', 
            'A vibrant celebration of music, band competitions, classical dance performances, and celebrity night.',
            d3, '17:00', '22:00', 'Open Air Theatre', 'Sports Complex', 'Coimbatore',
            'Cultural', 0.00, 0, 500, 120, dl3,
            'https://images.unsplash.com/photo-1501281668745-f7f57925c3b4?auto=format&fit=crop&q=80&w=800',
            'cultural@eventorg.com', '+91 98765 43212', 'College ID mandatory for entry',
            'music, dance, festival, fun', 'PUBLISHED', None
        ),
        (
            org_id,
            'Startup Summit & Angel Pitch 2026', 
            'Connect student founders with venture capitalists, learn pitch deck strategies, and witness live angel pitches.',
            d4, '11:00', '15:30', 'Executive Convention Hall', 'Innovation Hub', 'Hyderabad',
            'Business', 0.00, 0, 100, 12, dl4,
            'https://images.unsplash.com/photo-1515187029135-18ee286d815b?auto=format&fit=crop&q=80&w=800',
            'startups@eventorg.com', '+91 98765 43213', 'Pitch deck submission if participating in pitching round',
            'business, startup, vc, pitch', 'PENDING_APPROVAL', None
        ),
        (
            org_id,
            'Cloud Native & DevOps Bootcamp 2026', 
            'Introductory bootcamp on Docker, Kubernetes, CI/CD pipelines and microservice architectures.',
            d5, '09:30', '16:30', 'Virtual / Lab 4', 'Computer Center', 'Online',
            'Workshop', 0.00, 0, 80, 75, dl5,
            'https://images.unsplash.com/photo-1517694712202-14dd9538aa97?auto=format&fit=crop&q=80&w=800',
            'devops@eventorg.com', '+91 98765 43214', 'Docker Desktop installed',
            'devops, docker, kubernetes, cloud', 'COMPLETED', None
        )
    ]

    for ev in events:
        cursor.execute("SELECT * FROM events WHERE title = ?", (ev[1],))
        existing_ev = cursor.fetchone()
        if not existing_ev:
            cursor.execute('''
                INSERT INTO events (
                    organizer_id, title, description, date, time, end_time, venue, address, city,
                    category, price, is_paid, max_participants, current_participants, deadline,
                    image_url, contact_email, contact_phone, requirements, tags, status, rejection_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ev)
            print(f"Added event: {ev[1]} ({ev[20]})")
        else:
            cursor.execute('''
                UPDATE events SET
                    date = ?, time = ?, end_time = ?, venue = ?, address = ?, city = ?,
                    category = ?, price = ?, is_paid = ?, max_participants = ?, deadline = ?,
                    status = ?, image_url = ?
                WHERE title = ?
            ''', (ev[3], ev[4], ev[5], ev[6], ev[7], ev[8], ev[9], ev[10], ev[11], ev[12], ev[14], ev[20], ev[15], ev[1]))

    db.commit()
    db.close()
    print("Database seeded with realistic multi-role data and events!")

if __name__ == '__main__':
    seed()
