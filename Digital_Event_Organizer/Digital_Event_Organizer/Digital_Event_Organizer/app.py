import os
import sqlite3
import csv
import io
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, Response, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

# Custom service modules
from services.email_service import (
    send_registration_confirmation, send_waitlist_promotion,
    send_event_cancellation, send_approval_status
)
from services.ticket_service import generate_ticket_code, generate_qr_image
from services.payment_service import process_payment, get_gateway_info
from services.calendar_service import generate_ics_content, generate_google_calendar_url

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'eventorg_secret_production_key_2026')

DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'event_organizer.db')

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON;")
    return db

# -------------------------------------------------------------
# Database Lifecycle & Startup Helpers
# -------------------------------------------------------------
def sync_event_lifecycle(db=None):
    """
    Automatically transitions event statuses based on current date/time:
    - If date < today and status is PUBLISHED or ONGOING -> mark COMPLETED
    """
    close_db = False
    if db is None:
        db = get_db()
        close_db = True

    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        db.execute('''
            UPDATE events 
            SET status = 'COMPLETED' 
            WHERE date < ? AND status IN ('PUBLISHED', 'ONGOING')
        ''', (today_str,))
        db.commit()
    except Exception as e:
        app.logger.warning(f"Lifecycle sync notice: {e}")
    finally:
        if close_db:
            db.close()

# -------------------------------------------------------------
# Notification Helper
# -------------------------------------------------------------
def create_notification(user_id, title, message, notif_type='info', link=None, db=None):
    """
    Creates an in-app notification record for a user.
    """
    close_db = False
    if db is None:
        db = get_db()
        close_db = True
    try:
        db.execute('''
            INSERT INTO notifications (user_id, title, message, type, link, is_read)
            VALUES (?, ?, ?, ?, ?, 0)
        ''', (user_id, title, message, notif_type, link))
        db.commit()
    except Exception as e:
        app.logger.error(f"Error creating notification: {e}")
    finally:
        if close_db:
            db.close()

# -------------------------------------------------------------
# Authentication & Authorization Decorators
# -------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login', next=request.path))
            
            user_role = session.get('role', 'attendee')
            # Treat legacy 'user' as 'attendee'
            if user_role == 'user':
                user_role = 'attendee'
                
            if user_role not in allowed_roles and 'admin' not in allowed_roles:
                flash('You do not have permission to view this page.', 'error')
                return redirect(url_for('dashboard'))
            elif user_role not in allowed_roles and user_role != 'admin':
                flash('Unauthorized access: insufficient permissions.', 'error')
                return redirect(url_for('dashboard'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# -------------------------------------------------------------
# Context Processors & Global Template Variables
# -------------------------------------------------------------
@app.context_processor
def inject_global_data():
    unread_count = 0
    if 'user_id' in session:
        try:
            db = get_db()
            row = db.execute(
                'SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0',
                (session['user_id'],)
            ).fetchone()
            if row:
                unread_count = row['cnt']
            db.close()
        except Exception:
            unread_count = 0
    return {
        'unread_notifications_count': unread_count,
        'current_year': datetime.now().year,
        'now_date': datetime.now().strftime('%Y-%m-%d')
    }

# -------------------------------------------------------------
# Core & Public Routes
# -------------------------------------------------------------
@app.route('/')
def home():
    db = get_db()
    sync_event_lifecycle(db)
    
    # 6 featured published upcoming events
    events = db.execute('''
        SELECT * FROM events 
        WHERE status = 'PUBLISHED' 
        ORDER BY date ASC LIMIT 6
    ''').fetchall()
    
    # Stats for homepage counter
    stats = {
        'events': db.execute('SELECT COUNT(*) as c FROM events WHERE status = "PUBLISHED"').fetchone()['c'],
        'users': db.execute('SELECT COUNT(*) as c FROM users WHERE role != "admin"').fetchone()['c'],
        'categories': db.execute('SELECT COUNT(*) as c FROM categories').fetchone()['c']
    }
    db.close()
    return render_template('home.html', events=events, stats=stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()
        
        if user and check_password_hash(user['password'], password):
            # Check if account is active
            if 'is_active' in user.keys() and not user['is_active']:
                flash('Your account has been deactivated. Please contact support.', 'error')
                return render_template('login.html')
            
            user_role = user['role']
            if user_role == 'user':
                user_role = 'attendee'
                
            session['user_id'] = user['user_id']
            session['name'] = user['name']
            session['email'] = user['email']
            session['role'] = user_role
            
            flash(f"Welcome back, {user['name']}!", 'success')
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
                
            if user_role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user_role == 'organizer':
                return redirect(url_for('organizer_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid email or password. Please try again.', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', 'attendee')
        
        if role not in ('attendee', 'organizer'):
            role = 'attendee'
            
        if not name or not email or not password:
            flash('Please fill in all required fields.', 'error')
            return render_template('register.html')
            
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('register.html')

        hashed_password = generate_password_hash(password)
        db = get_db()
        account = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if account:
            db.close()
            flash('An account with this email address already exists.', 'error')
            return render_template('register.html')
            
        cursor = db.execute('''
            INSERT INTO users (name, email, password, role, is_active)
            VALUES (?, ?, ?, ?, 1)
        ''', (name, email, hashed_password, role))
        new_user_id = cursor.lastrowid
        db.commit()
        
        create_notification(
            new_user_id,
            "Welcome to EventOrg!",
            f"Hi {name}, your account has been created successfully as an {role.capitalize()}.",
            "success",
            db=db
        )
        db.close()
        
        flash('Registration successful! Please log in with your credentials.', 'success')
        return redirect(url_for('login'))
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been safely logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role', 'attendee')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'organizer':
        return redirect(url_for('organizer_dashboard'))
    return redirect(url_for('user_dashboard'))

# -------------------------------------------------------------
# Explore Events with Multi-Filter & Search
# -------------------------------------------------------------
@app.route('/events')
def events():
    db = get_db()
    sync_event_lifecycle(db)
    
    # Extract query filters
    search_query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    date_filter = request.args.get('date_filter', 'all')
    location = request.args.get('location', '').strip()
    price_filter = request.args.get('price_type', 'all') # all, free, paid
    availability = request.args.get('availability', 'all') # all, available

    # Build SQL dynamically
    sql = "SELECT * FROM events WHERE status IN ('PUBLISHED', 'COMPLETED')"
    params = []

    if search_query:
        sql += " AND (title LIKE ? OR description LIKE ? OR venue LIKE ? OR tags LIKE ?)"
        wildcard = f"%{search_query}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])

    if category and category != 'all':
        sql += " AND category = ?"
        params.append(category)

    if location:
        sql += " AND (city LIKE ? OR venue LIKE ?)"
        params.extend([f"%{location}%", f"%{location}%"])

    if price_filter == 'free':
        sql += " AND is_paid = 0"
    elif price_filter == 'paid':
        sql += " AND is_paid = 1"

    if availability == 'available':
        sql += " AND current_participants < max_participants AND status = 'PUBLISHED'"

    today = datetime.now().date()
    if date_filter == 'today':
        sql += " AND date = ?"
        params.append(today.strftime('%Y-%m-%d'))
    elif date_filter == 'this_week':
        end_week = today + timedelta(days=7)
        sql += " AND date BETWEEN ? AND ?"
        params.extend([today.strftime('%Y-%m-%d'), end_week.strftime('%Y-%m-%d')])
    elif date_filter == 'this_month':
        end_month = today + timedelta(days=30)
        sql += " AND date BETWEEN ? AND ?"
        params.extend([today.strftime('%Y-%m-%d'), end_month.strftime('%Y-%m-%d')])
    elif date_filter == 'past':
        sql += " AND (date < ? OR status = 'COMPLETED')"
        params.append(today.strftime('%Y-%m-%d'))
    else:
        # Default: show upcoming first, then completed
        sql += " ORDER BY CASE WHEN status = 'PUBLISHED' THEN 0 ELSE 1 END, date ASC"

    if date_filter != 'all' and not sql.endswith("ASC"):
        sql += " ORDER BY date ASC"

    all_events = db.execute(sql, params).fetchall()
    categories = db.execute('SELECT * FROM categories ORDER BY name ASC').fetchall()
    db.close()

    return render_template(
        'events.html',
        events=all_events,
        categories=categories,
        filters={
            'q': search_query,
            'category': category,
            'date_filter': date_filter,
            'location': location,
            'price_type': price_filter,
            'availability': availability
        }
    )

@app.route('/event/<int:id>')
def event_detail(id):
    db = get_db()
    sync_event_lifecycle(db)
    
    event = db.execute('''
        SELECT e.*, u.name as organizer_name, u.email as organizer_email 
        FROM events e 
        LEFT JOIN users u ON e.organizer_id = u.user_id 
        WHERE e.event_id = ?
    ''', (id,)).fetchone()
    
    if not event:
        db.close()
        flash('Event not found.', 'error')
        return redirect(url_for('events'))

    # Permission check for unpublished events
    if event['status'] in ('DRAFT', 'PENDING_APPROVAL', 'REJECTED'):
        if 'user_id' not in session or (session.get('role') != 'admin' and session.get('user_id') != event['organizer_id']):
            db.close()
            flash('This event is currently undergoing administrative review.', 'info')
            return redirect(url_for('events'))

    # Fetch reviews & average rating
    reviews = db.execute('''
        SELECT r.*, u.name as user_name 
        FROM reviews r 
        JOIN users u ON r.user_id = u.user_id 
        WHERE r.event_id = ? 
        ORDER BY r.created_at DESC
    ''', (id,)).fetchall()

    avg_rating_row = db.execute('''
        SELECT AVG(rating) as avg_rating, COUNT(*) as count 
        FROM reviews WHERE event_id = ?
    ''', (id,)).fetchone()
    avg_rating = round(avg_rating_row['avg_rating'], 1) if avg_rating_row and avg_rating_row['avg_rating'] else 0
    review_count = avg_rating_row['count'] if avg_rating_row else 0

    # User registration status if logged in
    user_reg = None
    can_review = False
    existing_review = None
    if 'user_id' in session:
        user_reg = db.execute('''
            SELECT * FROM registrations 
            WHERE user_id = ? AND event_id = ? AND status != 'CANCELLED'
        ''', (session['user_id'], id)).fetchone()
        
        # User can review only if attended
        attended_reg = db.execute('''
            SELECT * FROM registrations 
            WHERE user_id = ? AND event_id = ? AND status = 'ATTENDED'
        ''', (session['user_id'], id)).fetchone()
        
        existing_review = db.execute('''
            SELECT * FROM reviews 
            WHERE user_id = ? AND event_id = ?
        ''', (session['user_id'], id)).fetchone()
        
        if attended_reg and not existing_review:
            can_review = True

    google_cal_url = generate_google_calendar_url(event)
    db.close()

    return render_template(
        'event_detail.html',
        event=event,
        reviews=reviews,
        avg_rating=avg_rating,
        review_count=review_count,
        user_reg=user_reg,
        can_review=can_review,
        existing_review=existing_review,
        google_cal_url=google_cal_url
    )

# -------------------------------------------------------------
# Registration & Waitlist System
# -------------------------------------------------------------
@app.route('/select_seats/<int:id>')
@login_required
def select_seats(id):
    db = get_db()
    event = db.execute('SELECT * FROM events WHERE event_id = ?', (id,)).fetchone()
    db.close()
    if not event:
        flash('Event not found.', 'error')
        return redirect(url_for('events'))
    return render_template('select_seats.html', event=event)

@app.route('/register_event/<int:id>', methods=['POST'])
@login_required
def register_event(id):
    user_id = session['user_id']
    db = get_db()
    sync_event_lifecycle(db)

    event = db.execute('SELECT * FROM events WHERE event_id = ?', (id,)).fetchone()
    if not event:
        db.close()
        flash('Event not found.', 'error')
        return redirect(url_for('events'))

    # 1. Verify event is published
    if event['status'] != 'PUBLISHED':
        db.close()
        flash(f"Cannot register for an event with status '{event['status']}'.", 'error')
        return redirect(url_for('event_detail', id=id))

    # 2. Verify registration deadline
    try:
        deadline_dt = datetime.strptime(str(event['deadline']).strip(), "%Y-%m-%d %H:%M:%S")
        if datetime.now() > deadline_dt:
            db.close()
            flash('Registration deadline for this event has passed.', 'error')
            return redirect(url_for('event_detail', id=id))
    except Exception:
        pass # Ignore deadline parsing if invalid format

    # 3. Prevent duplicate active registrations
    existing_reg = db.execute('''
        SELECT * FROM registrations 
        WHERE user_id = ? AND event_id = ? AND status IN ('CONFIRMED', 'WAITLISTED', 'ATTENDED', 'PENDING')
    ''', (user_id, id)).fetchone()

    if existing_reg:
        db.close()
        if existing_reg['status'] == 'WAITLISTED':
            flash('You are already on the waitlist for this event.', 'info')
        else:
            flash('You are already registered for this event.', 'info')
        return redirect(url_for('event_detail', id=id))

    # 4. Check Capacity: Confirmed vs Waitlist
    is_full = event['current_participants'] >= event['max_participants']
    
    if is_full:
        # Put on waitlist
        cursor = db.execute('''
            INSERT INTO registrations (user_id, event_id, status, payment_status)
            VALUES (?, ?, 'WAITLISTED', 'unpaid')
        ''', (user_id, id))
        db.commit()
        
        create_notification(
            user_id,
            "Added to Waitlist",
            f"Event '{event['title']}' is currently full. You have been added to the waitlist. You will be automatically enrolled if a seat opens up!",
            "warning",
            link=url_for('user_dashboard'),
            db=db
        )
        db.close()
        flash('This event is currently full. You have been placed on the priority waitlist!', 'info')
        return redirect(url_for('user_dashboard'))

    # If it's a paid event, redirect to payment gateway flow
    if event['is_paid']:
        db.close()
        return redirect(url_for('payment_checkout', event_id=id))

    # Free Event -> Immediate Confirmation
    ticket_code = generate_ticket_code(id, user_id)
    qr_data, qr_uri, qr_path = generate_qr_image(ticket_code, id, user_id)

    cursor = db.execute('''
        INSERT INTO registrations (user_id, event_id, status, payment_status, ticket_code)
        VALUES (?, ?, 'CONFIRMED', 'paid', ?)
    ''', (user_id, id, ticket_code))
    reg_id = cursor.lastrowid

    # Create digital ticket record
    db.execute('''
        INSERT INTO tickets (registration_id, ticket_code, event_id, user_id, qr_data, qr_path, status)
        VALUES (?, ?, ?, ?, ?, ?, 'VALID')
    ''', (reg_id, ticket_code, id, user_id, qr_data, qr_path))

    # Increment participants count
    db.execute('''
        UPDATE events 
        SET current_participants = current_participants + 1 
        WHERE event_id = ?
    ''', (id,))

    # In-app notification
    create_notification(
        user_id,
        "Registration Confirmed!",
        f"You are registered for {event['title']}. Ticket ID: {ticket_code}",
        "success",
        link=url_for('view_ticket', ticket_code=ticket_code),
        db=db
    )

    db.commit()

    # Email notification
    send_registration_confirmation(
        session.get('email', ''),
        session.get('name', 'Attendee'),
        event['title'],
        ticket_code,
        event['date'],
        event['venue']
    )

    db.close()
    flash(f'Registration successful! Your ticket code is {ticket_code}.', 'success')
    return redirect(url_for('view_ticket', ticket_code=ticket_code))

@app.route('/cancel_registration/<int:reg_id>', methods=['POST'])
@login_required
def cancel_registration(reg_id):
    user_id = session['user_id']
    user_role = session.get('role', 'attendee')
    db = get_db()

    reg = db.execute('SELECT * FROM registrations WHERE registration_id = ?', (reg_id,)).fetchone()
    if not reg:
        db.close()
        flash('Registration record not found.', 'error')
        return redirect(url_for('user_dashboard'))

    # Security: Only owner or admin can cancel
    if reg['user_id'] != user_id and user_role != 'admin':
        db.close()
        flash('Unauthorized to modify this registration.', 'error')
        return redirect(url_for('user_dashboard'))

    event_id = reg['event_id']
    was_confirmed = reg['status'] == 'CONFIRMED'

    # Mark cancelled
    db.execute("UPDATE registrations SET status = 'CANCELLED' WHERE registration_id = ?", (reg_id,))
    db.execute("UPDATE tickets SET status = 'CANCELLED' WHERE registration_id = ?", (reg_id,))

    if was_confirmed:
        # Decrement participants
        db.execute('''
            UPDATE events 
            SET current_participants = MAX(0, current_participants - 1) 
            WHERE event_id = ?
        ''', (event_id,))

        # Promote earliest waitlisted user
        waitlisted = db.execute('''
            SELECT r.*, u.name, u.email, e.title 
            FROM registrations r 
            JOIN users u ON r.user_id = u.user_id 
            JOIN events e ON r.event_id = e.event_id 
            WHERE r.event_id = ? AND r.status = 'WAITLISTED' 
            ORDER BY r.registration_id ASC LIMIT 1
        ''', (event_id,)).fetchone()

        if waitlisted:
            promoted_uid = waitlisted['user_id']
            promoted_reg_id = waitlisted['registration_id']
            new_ticket_code = generate_ticket_code(event_id, promoted_uid)
            qr_data, qr_uri, qr_path = generate_qr_image(new_ticket_code, event_id, promoted_uid)

            db.execute('''
                UPDATE registrations 
                SET status = 'CONFIRMED', payment_status = 'paid', ticket_code = ? 
                WHERE registration_id = ?
            ''', (new_ticket_code, promoted_reg_id))

            db.execute('''
                INSERT INTO tickets (registration_id, ticket_code, event_id, user_id, qr_data, qr_path, status)
                VALUES (?, ?, ?, ?, ?, ?, 'VALID')
            ''', (promoted_reg_id, new_ticket_code, event_id, promoted_uid, qr_data, qr_path))

            db.execute('''
                UPDATE events 
                SET current_participants = current_participants + 1 
                WHERE event_id = ?
            ''', (event_id,))

            create_notification(
                promoted_uid,
                "Promoted from Waitlist!",
                f"A seat became available! You are now CONFIRMED for '{waitlisted['title']}'. Ticket ID: {new_ticket_code}",
                "success",
                link=url_for('view_ticket', ticket_code=new_ticket_code),
                db=db
            )

            send_waitlist_promotion(
                waitlisted['email'],
                waitlisted['name'],
                waitlisted['title'],
                new_ticket_code
            )

    create_notification(
        reg['user_id'],
        "Registration Cancelled",
        "Your registration has been cancelled successfully.",
        "info",
        db=db
    )

    db.commit()
    db.close()
    flash('Registration has been cancelled successfully.', 'info')
    return redirect(url_for('user_dashboard'))

# -------------------------------------------------------------
# Payment Flow (Sandbox & Architecture Support)
# -------------------------------------------------------------
@app.route('/payment/<int:event_id>', methods=['GET', 'POST'])
@login_required
def payment_checkout(event_id):
    user_id = session['user_id']
    db = get_db()
    sync_event_lifecycle(db)

    event = db.execute('SELECT * FROM events WHERE event_id = ?', (event_id,)).fetchone()
    if not event:
        db.close()
        flash('Event not found.', 'error')
        return redirect(url_for('events'))

    if event['status'] != 'PUBLISHED':
        db.close()
        flash('This event is not open for registration.', 'error')
        return redirect(url_for('events'))

    gateway_info = get_gateway_info()

    if request.method == 'POST':
        payment_method = request.form.get('payment_method', 'card')
        
        # Check capacity once more before payment
        if event['current_participants'] >= event['max_participants']:
            db.close()
            flash('Unfortunately this event reached capacity while checking out. Please join the waitlist.', 'warning')
            return redirect(url_for('event_detail', id=event_id))

        # Invoke payment service layer
        result = process_payment(event['price'], user_id, event_id, payment_method)

        if result.get('success'):
            txn_id = result['transaction_id']
            ticket_code = generate_ticket_code(event_id, user_id)
            qr_data, qr_uri, qr_path = generate_qr_image(ticket_code, event_id, user_id)

            cursor = db.execute('''
                INSERT INTO registrations (user_id, event_id, status, payment_status, ticket_code)
                VALUES (?, ?, 'CONFIRMED', 'paid', ?)
            ''', (user_id, event_id, ticket_code))
            reg_id = cursor.lastrowid

            db.execute('''
                INSERT INTO tickets (registration_id, ticket_code, event_id, user_id, qr_data, qr_path, status)
                VALUES (?, ?, ?, ?, ?, ?, 'VALID')
            ''', (reg_id, ticket_code, event_id, user_id, qr_data, qr_path))

            db.execute('''
                INSERT INTO payments (registration_id, user_id, amount, transaction_id, payment_status)
                VALUES (?, ?, ?, ?, 'paid')
            ''', (reg_id, user_id, event['price'], txn_id))

            db.execute('UPDATE events SET current_participants = current_participants + 1 WHERE event_id = ?', (event_id,))

            create_notification(
                user_id,
                "Payment & Registration Successful",
                f"Paid Rs. {event['price']} for {event['title']}. Txn ID: {txn_id}. Ticket: {ticket_code}",
                "success",
                link=url_for('view_ticket', ticket_code=ticket_code),
                db=db
            )

            db.commit()

            send_registration_confirmation(
                session.get('email', ''),
                session.get('name', 'Attendee'),
                event['title'],
                ticket_code,
                event['date'],
                event['venue']
            )

            db.close()
            flash(f"Payment successful! Transaction ID: {txn_id}", 'success')
            return redirect(url_for('view_ticket', ticket_code=ticket_code))
        else:
            db.close()
            flash(f"Payment failed: {result.get('message', 'Please try again.')}", 'error')
            return redirect(url_for('payment_checkout', event_id=event_id))

    db.close()
    return render_template('payment.html', event=event, gateway_info=gateway_info)

# -------------------------------------------------------------
# Digital Tickets & Mobile QR Code Views
# -------------------------------------------------------------
@app.route('/tickets')
@app.route('/user/tickets')
@login_required
def my_tickets():
    user_id = session['user_id']
    db = get_db()
    tickets = db.execute('''
        SELECT t.*, e.title, e.date, e.time, e.end_time, e.venue, e.address, e.city, e.image_url,
               r.status as registration_status, r.checked_in_at
        FROM tickets t
        JOIN events e ON t.event_id = e.event_id
        JOIN registrations r ON t.registration_id = r.registration_id
        WHERE t.user_id = ?
        ORDER BY e.date DESC
    ''', (user_id,)).fetchall()
    db.close()
    return render_template('user/tickets.html', tickets=tickets)

@app.route('/ticket/<ticket_code>')
def view_ticket(ticket_code):
    db = get_db()
    ticket = db.execute('''
        SELECT t.*, e.title, e.description, e.date, e.time, e.end_time, e.venue, e.address, e.city, e.image_url,
               u.name as attendee_name, u.email as attendee_email,
               r.status as registration_status, r.payment_status, r.checked_in_at
        FROM tickets t
        JOIN events e ON t.event_id = e.event_id
        JOIN users u ON t.user_id = u.user_id
        JOIN registrations r ON t.registration_id = r.registration_id
        WHERE t.ticket_code = ?
    ''', (ticket_code,)).fetchone()
    db.close()

    if not ticket:
        flash('Ticket not found or invalid ticket code.', 'error')
        return redirect(url_for('home'))

    # Ensure user can only view their own ticket unless admin/organizer
    if 'user_id' in session:
        is_privileged = session.get('role') in ('admin', 'organizer')
        if ticket['user_id'] != session['user_id'] and not is_privileged:
            flash('Access restricted to ticket owner.', 'error')
            return redirect(url_for('user_dashboard'))

    return render_template('user/ticket_detail.html', ticket=ticket)

# -------------------------------------------------------------
# Attendee Dashboard
# -------------------------------------------------------------
@app.route('/user/dashboard')
@login_required
def user_dashboard():
    user_id = session['user_id']
    db = get_db()
    sync_event_lifecycle(db)

    # Active registrations
    registrations = db.execute('''
        SELECT r.*, e.title, e.date, e.time, e.venue, e.status as event_status, e.is_paid, e.price,
               t.ticket_code 
        FROM registrations r 
        JOIN events e ON r.event_id = e.event_id 
        LEFT JOIN tickets t ON r.registration_id = t.registration_id
        WHERE r.user_id = ? AND r.status != 'CANCELLED'
        ORDER BY e.date ASC
    ''', (user_id,)).fetchall()

    # Waitlisted registrations
    waitlisted = db.execute('''
        SELECT r.*, e.title, e.date, e.time, e.venue, e.status as event_status 
        FROM registrations r 
        JOIN events e ON r.event_id = e.event_id 
        WHERE r.user_id = ? AND r.status = 'WAITLISTED'
        ORDER BY r.registration_date DESC
    ''', (user_id,)).fetchall()

    # Past attended events
    past_events = db.execute('''
        SELECT r.*, e.title, e.date, e.time, e.venue, rev.rating as user_rating 
        FROM registrations r 
        JOIN events e ON r.event_id = e.event_id 
        LEFT JOIN reviews rev ON (r.event_id = rev.event_id AND rev.user_id = r.user_id)
        WHERE r.user_id = ? AND (r.status = 'ATTENDED' OR e.status = 'COMPLETED')
        ORDER BY e.date DESC
    ''', (user_id,)).fetchall()

    # Notifications
    notifications = db.execute('''
        SELECT * FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC LIMIT 20
    ''', (user_id,)).fetchall()

    db.close()
    return render_template(
        'user/dashboard.html',
        registrations=registrations,
        waitlisted=waitlisted,
        past_events=past_events,
        notifications=notifications
    )

# -------------------------------------------------------------
# Event Reviews & Ratings
# -------------------------------------------------------------
@app.route('/event/<int:id>/review', methods=['POST'])
@login_required
def submit_review(id):
    user_id = session['user_id']
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not rating or rating < 1 or rating > 5:
        flash('Please provide a valid rating between 1 and 5 stars.', 'error')
        return redirect(url_for('event_detail', id=id))

    db = get_db()
    # Check if attended
    reg = db.execute('''
        SELECT * FROM registrations 
        WHERE user_id = ? AND event_id = ? AND status = 'ATTENDED'
    ''', (user_id, id)).fetchone()

    if not reg:
        db.close()
        flash('Only verified attendees who checked in can leave a review.', 'error')
        return redirect(url_for('event_detail', id=id))

    try:
        db.execute('''
            INSERT INTO reviews (event_id, user_id, rating, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(event_id, user_id) DO UPDATE SET rating = ?, comment = ?, created_at = CURRENT_TIMESTAMP
        ''', (id, user_id, rating, comment, rating, comment))
        db.commit()
        flash('Thank you! Your review has been submitted.', 'success')
    except Exception as e:
        flash(f'Error submitting review: {e}', 'error')
    finally:
        db.close()

    return redirect(url_for('event_detail', id=id))

# -------------------------------------------------------------
# Calendar Integration (.ics & Google Calendar)
# -------------------------------------------------------------
@app.route('/event/<int:id>/calendar.ics')
def export_ics(id):
    db = get_db()
    event = db.execute('SELECT * FROM events WHERE event_id = ?', (id,)).fetchone()
    db.close()

    if not event:
        abort(404)

    ics_content = generate_ics_content(dict(event))
    filename = f"event_{id}.ics"
    return Response(
        ics_content,
        mimetype="text/calendar",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# -------------------------------------------------------------
# In-App Notifications API
# -------------------------------------------------------------
@app.route('/notifications')
@login_required
def notifications_page():
    user_id = session['user_id']
    db = get_db()
    notes = db.execute('''
        SELECT * FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (user_id,)).fetchall()
    db.close()
    return render_template('user/notifications.html', notifications=notes)

@app.route('/notifications/mark-read/<int:id>', methods=['POST'])
@login_required
def mark_notification_read(id):
    db = get_db()
    db.execute('UPDATE notifications SET is_read = 1 WHERE notification_id = ? AND user_id = ?',
               (id, session['user_id']))
    db.commit()
    db.close()
    if request.is_json:
        return jsonify({'success': True})
    return redirect(request.referrer or url_for('user_dashboard'))

@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    db = get_db()
    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
    db.commit()
    db.close()
    flash('All notifications marked as read.', 'success')
    return redirect(request.referrer or url_for('user_dashboard'))

@app.route('/api/notifications/unread-count')
def api_unread_notifications():
    if 'user_id' not in session:
        return jsonify({'unread_count': 0})
    db = get_db()
    row = db.execute('SELECT COUNT(*) as c FROM notifications WHERE user_id = ? AND is_read = 0',
                     (session['user_id'],)).fetchone()
    db.close()
    return jsonify({'unread_count': row['c'] if row else 0})

# -------------------------------------------------------------
# ORGANIZER PORTAL
# -------------------------------------------------------------
@app.route('/organizer/dashboard')
@role_required('organizer', 'admin')
def organizer_dashboard():
    user_id = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()
    sync_event_lifecycle(db)

    query = '''
        SELECT e.*, 
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.event_id AND r.status != 'CANCELLED') as reg_count,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.event_id AND r.status = 'ATTENDED') as attend_count
        FROM events e
    '''
    if not is_admin:
        query += " WHERE e.organizer_id = ?"
        events = db.execute(query + " ORDER BY e.created_at DESC", (user_id,)).fetchall()
    else:
        events = db.execute(query + " ORDER BY e.created_at DESC").fetchall()

    # Aggregate Statistics
    total_events = len(events)
    published_events = sum(1 for e in events if e['status'] == 'PUBLISHED')
    pending_events = sum(1 for e in events if e['status'] == 'PENDING_APPROVAL')
    total_registrations = sum(e['reg_count'] for e in events)
    total_attendance = sum(e['attend_count'] for e in events)

    db.close()
    return render_template(
        'organizer/dashboard.html',
        events=events,
        stats={
            'total_events': total_events,
            'published_events': published_events,
            'pending_events': pending_events,
            'total_registrations': total_registrations,
            'total_attendance': total_attendance
        }
    )

@app.route('/organizer/create_event', methods=['GET', 'POST'])
@app.route('/admin/create_event', methods=['GET', 'POST'])
@role_required('organizer', 'admin')
def create_event():
    user_id = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'Tech').strip()
        date = request.form.get('date', '').strip()
        time = request.form.get('time', '').strip()
        end_time = request.form.get('end_time', '').strip()
        venue = request.form.get('venue', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        max_participants = int(request.form.get('max_participants', 100))
        is_paid = 1 if 'is_paid' in request.form else 0
        price = float(request.form.get('price', 0.00)) if is_paid else 0.00
        deadline = request.form.get('deadline', '').strip()
        image_url = request.form.get('image_url', '').strip()
        contact_email = request.form.get('contact_email', session.get('email', '')).strip()
        contact_phone = request.form.get('contact_phone', '').strip()
        requirements = request.form.get('requirements', '').strip()
        tags = request.form.get('tags', '').strip()

        # Action: Draft vs Submit for Approval vs Direct Publish (Admin)
        action = request.form.get('action', 'submit')

        # Validation
        if not title or not description or not date or not time or not venue or not deadline:
            flash('Please fill in all mandatory event fields.', 'error')
            categories = db.execute('SELECT * FROM categories ORDER BY name ASC').fetchall()
            db.close()
            return render_template('organizer/create_event.html', categories=categories)

        if max_participants <= 0:
            flash('Maximum capacity must be greater than 0.', 'error')
            categories = db.execute('SELECT * FROM categories ORDER BY name ASC').fetchall()
            db.close()
            return render_template('organizer/create_event.html', categories=categories)

        # Determine status
        if action == 'draft':
            status = 'DRAFT'
        elif is_admin and action == 'publish':
            status = 'PUBLISHED'
        else:
            status = 'PENDING_APPROVAL'

        cursor = db.execute('''
            INSERT INTO events (
                organizer_id, title, description, category, date, time, end_time,
                venue, address, city, max_participants, current_participants,
                is_paid, price, deadline, image_url, contact_email, contact_phone,
                requirements, tags, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, title, description, category, date, time, end_time,
            venue, address, city, max_participants, is_paid, price, deadline,
            image_url, contact_email, contact_phone, requirements, tags, status
        ))
        new_event_id = cursor.lastrowid
        db.commit()

        if status == 'PENDING_APPROVAL':
            # Notify all admins of pending approval
            admins = db.execute("SELECT user_id FROM users WHERE role = 'admin'").fetchall()
            for admin_row in admins:
                create_notification(
                    admin_row['user_id'],
                    "New Event Pending Approval",
                    f"'{title}' submitted by {session.get('name')}.",
                    "info",
                    link=url_for('admin_approvals'),
                    db=db
                )
            flash(f"Event '{title}' created and submitted for Admin approval.", 'success')
        elif status == 'DRAFT':
            flash(f"Event '{title}' saved as Draft.", 'info')
        else:
            flash(f"Event '{title}' published successfully!", 'success')

        db.close()
        if is_admin and request.path.startswith('/admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('organizer_dashboard'))

    categories = db.execute('SELECT * FROM categories ORDER BY name ASC').fetchall()
    db.close()
    return render_template('organizer/create_event.html', categories=categories)

@app.route('/organizer/edit_event/<int:id>', methods=['GET', 'POST'])
@app.route('/admin/edit_event/<int:id>', methods=['GET', 'POST'])
@role_required('organizer', 'admin')
def edit_event(id):
    user_id = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()

    event = db.execute('SELECT * FROM events WHERE event_id = ?', (id,)).fetchone()
    if not event:
        db.close()
        flash('Event not found.', 'error')
        return redirect(url_for('organizer_dashboard'))

    if not is_admin and event['organizer_id'] != user_id:
        db.close()
        flash('Unauthorized to edit this event.', 'error')
        return redirect(url_for('organizer_dashboard'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'Tech').strip()
        date = request.form.get('date', '').strip()
        time = request.form.get('time', '').strip()
        end_time = request.form.get('end_time', '').strip()
        venue = request.form.get('venue', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        max_participants = int(request.form.get('max_participants', 100))
        is_paid = 1 if 'is_paid' in request.form else 0
        price = float(request.form.get('price', 0.00)) if is_paid else 0.00
        deadline = request.form.get('deadline', '').strip()
        image_url = request.form.get('image_url', '').strip()
        contact_email = request.form.get('contact_email', '').strip()
        contact_phone = request.form.get('contact_phone', '').strip()
        requirements = request.form.get('requirements', '').strip()
        tags = request.form.get('tags', '').strip()
        action = request.form.get('action', 'submit')

        # Status transition handling
        new_status = event['status']
        if action == 'draft':
            new_status = 'DRAFT'
        elif action == 'submit' and event['status'] in ('DRAFT', 'REJECTED'):
            new_status = 'PENDING_APPROVAL'
        elif is_admin and action == 'publish':
            new_status = 'PUBLISHED'

        db.execute('''
            UPDATE events SET
                title = ?, description = ?, category = ?, date = ?, time = ?, end_time = ?,
                venue = ?, address = ?, city = ?, max_participants = ?, is_paid = ?,
                price = ?, deadline = ?, image_url = ?, contact_email = ?, contact_phone = ?,
                requirements = ?, tags = ?, status = ?
            WHERE event_id = ?
        ''', (
            title, description, category, date, time, end_time,
            venue, address, city, max_participants, is_paid,
            price, deadline, image_url, contact_email, contact_phone,
            requirements, tags, new_status, id
        ))
        db.commit()
        db.close()
        flash('Event details updated successfully.', 'success')
        if is_admin and request.path.startswith('/admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('organizer_dashboard'))

    categories = db.execute('SELECT * FROM categories ORDER BY name ASC').fetchall()
    db.close()
    return render_template('organizer/edit_event.html', event=event, categories=categories)

@app.route('/organizer/cancel_event/<int:id>', methods=['POST'])
@app.route('/admin/delete_event/<int:id>', methods=['GET', 'POST'])
@role_required('organizer', 'admin')
def cancel_or_delete_event(id):
    user_id = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()

    event = db.execute('SELECT * FROM events WHERE event_id = ?', (id,)).fetchone()
    if not event:
        db.close()
        flash('Event not found.', 'error')
        return redirect(url_for('organizer_dashboard'))

    if not is_admin and event['organizer_id'] != user_id:
        db.close()
        flash('Unauthorized to manage this event.', 'error')
        return redirect(url_for('organizer_dashboard'))

    # Mark as CANCELLED rather than deleting completely so registration records remain clean
    db.execute("UPDATE events SET status = 'CANCELLED' WHERE event_id = ?", (id,))
    
    # Notify registered attendees
    attendees = db.execute('''
        SELECT u.email, u.name, u.user_id 
        FROM registrations r 
        JOIN users u ON r.user_id = u.user_id 
        WHERE r.event_id = ? AND r.status != 'CANCELLED'
    ''', (id,)).fetchall()

    for att in attendees:
        create_notification(
            att['user_id'],
            "Event Cancelled",
            f"The event '{event['title']}' has been cancelled by the organizer.",
            "danger",
            db=db
        )
        send_event_cancellation(att['email'], att['name'], event['title'])

    db.commit()
    db.close()
    flash(f"Event '{event['title']}' has been cancelled and attendees have been notified.", 'info')
    if is_admin:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('organizer_dashboard'))

@app.route('/organizer/view_participants/<int:id>')
@app.route('/admin/view_participants/<int:id>')
@role_required('organizer', 'admin')
def view_participants(id):
    user_id = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()

    event = db.execute('SELECT * FROM events WHERE event_id = ?', (id,)).fetchone()
    if not event:
        db.close()
        flash('Event not found.', 'error')
        return redirect(url_for('organizer_dashboard'))

    if not is_admin and event['organizer_id'] != user_id:
        db.close()
        flash('Unauthorized to view participants for this event.', 'error')
        return redirect(url_for('organizer_dashboard'))

    participants = db.execute('''
        SELECT r.registration_id, r.registration_date, r.status, r.payment_status,
               r.ticket_code, r.checked_in_at, u.name, u.email
        FROM registrations r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.event_id = ?
        ORDER BY r.registration_date DESC
    ''', (id,)).fetchall()

    db.close()
    return render_template(
        'organizer/participants.html',
        participants=participants,
        event=event,
        is_admin=is_admin
    )

# -------------------------------------------------------------
# QR Code Check-In & Scanner
# -------------------------------------------------------------
@app.route('/organizer/checkin')
@app.route('/organizer/checkin/<int:event_id>')
@role_required('organizer', 'admin')
def checkin_page(event_id=None):
    user_id = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()

    if is_admin:
        events = db.execute("SELECT * FROM events WHERE status IN ('PUBLISHED', 'COMPLETED') ORDER BY date DESC").fetchall()
    else:
        events = db.execute("SELECT * FROM events WHERE organizer_id = ? AND status IN ('PUBLISHED', 'COMPLETED') ORDER BY date DESC", (user_id,)).fetchall()

    selected_event = None
    if event_id:
        selected_event = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()

    db.close()
    return render_template('organizer/checkin.html', events=events, selected_event=selected_event)

@app.route('/api/checkin/verify', methods=['POST'])
@role_required('organizer', 'admin')
def api_verify_checkin():
    """
    Scans/Validates ticket code and marks attendee as ATTENDED.
    """
    data = request.get_json(silent=True) or request.form
    ticket_input = data.get('ticket_code', '').strip()
    target_event_id = data.get('event_id')

    if not ticket_input:
        return jsonify({'success': False, 'message': 'Missing ticket code.'}), 400

    # If QR payload contains JSON: {"ticket_code": "...", ...}
    import json
    try:
        parsed = json.loads(ticket_input)
        if isinstance(parsed, dict) and 'ticket_code' in parsed:
            ticket_input = parsed['ticket_code']
    except Exception:
        pass

    db = get_db()
    ticket = db.execute('''
        SELECT t.*, r.status as reg_status, r.checked_in_at,
               u.name as attendee_name, u.email as attendee_email,
               e.title as event_title, e.event_id, e.organizer_id, e.date as event_date
        FROM tickets t
        JOIN registrations r ON t.registration_id = r.registration_id
        JOIN users u ON t.user_id = u.user_id
        JOIN events e ON t.event_id = e.event_id
        WHERE t.ticket_code = ?
    ''', (ticket_input,)).fetchone()

    if not ticket:
        db.close()
        return jsonify({'success': False, 'message': 'Invalid Ticket ID. No matching ticket found.'}), 404

    # Authorization: check organizer owns the event
    is_admin = session.get('role') == 'admin'
    if not is_admin and ticket['organizer_id'] != session['user_id']:
        db.close()
        return jsonify({'success': False, 'message': 'Unauthorized: This ticket belongs to an event you do not organize.'}), 403

    # Event mismatch check if specific event selected
    if target_event_id and str(ticket['event_id']) != str(target_event_id):
        db.close()
        return jsonify({'success': False, 'message': f"Ticket belongs to '{ticket['event_title']}', not selected event."}), 400

    # Check if registration was cancelled
    if ticket['reg_status'] == 'CANCELLED':
        db.close()
        return jsonify({'success': False, 'message': 'This registration has been cancelled.'}), 400

    # Check if already checked in
    if ticket['reg_status'] == 'ATTENDED' or ticket['checked_in_at']:
        db.close()
        return jsonify({
            'success': False,
            'already_checked_in': True,
            'message': f"Already Checked In at {ticket['checked_in_at'] or 'earlier'}.",
            'attendee': ticket['attendee_name'],
            'event': ticket['event_title']
        }), 200

    # Mark as ATTENDED
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute('''
        UPDATE registrations 
        SET status = 'ATTENDED', checked_in_at = ? 
        WHERE registration_id = ?
    ''', (now_str, ticket['registration_id']))
    db.execute("UPDATE tickets SET status = 'USED' WHERE ticket_id = ?", (ticket['ticket_id'],))

    create_notification(
        ticket['user_id'],
        "Checked In!",
        f"You have been successfully checked in for {ticket['event_title']} at {now_str}.",
        "success",
        db=db
    )

    db.commit()
    db.close()

    return jsonify({
        'success': True,
        'message': f"Check-in Successful!",
        'attendee': ticket['attendee_name'],
        'email': ticket['attendee_email'],
        'event': ticket['event_title'],
        'timestamp': now_str
    })

# -------------------------------------------------------------
# ADMIN PORTAL
# -------------------------------------------------------------
@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    db = get_db()
    sync_event_lifecycle(db)

    # Real metric counts
    total_events = db.execute('SELECT COUNT(*) as count FROM events').fetchone()['count']
    total_users = db.execute('SELECT COUNT(*) as count FROM users WHERE role != "admin"').fetchone()['count']
    total_registrations = db.execute('SELECT COUNT(*) as count FROM registrations WHERE status != "CANCELLED"').fetchone()['count']
    total_attendance = db.execute("SELECT COUNT(*) as count FROM registrations WHERE status = 'ATTENDED'").fetchone()['count']
    pending_approvals = db.execute("SELECT COUNT(*) as count FROM events WHERE status = 'PENDING_APPROVAL'").fetchone()['count']

    # Events grouped by category
    categories_stat = db.execute('''
        SELECT category, COUNT(*) as count 
        FROM events 
        GROUP BY category
    ''').fetchall()

    # Events list
    events = db.execute('''
        SELECT e.*, u.name as organizer_name,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.event_id AND r.status != 'CANCELLED') as reg_count
        FROM events e 
        LEFT JOIN users u ON e.organizer_id = u.user_id 
        ORDER BY e.created_at DESC
    ''').fetchall()

    db.close()
    return render_template(
        'admin/dashboard.html',
        events=events,
        total_events=total_events,
        user_count=total_users,
        reg_count=total_registrations,
        total_attendance=total_attendance,
        pending_approvals=pending_approvals,
        categories_stat=categories_stat
    )

@app.route('/admin/users')
@role_required('admin')
def admin_users():
    db = get_db()
    users = db.execute('''
        SELECT u.*, 
               (SELECT COUNT(*) FROM registrations r WHERE r.user_id = u.user_id) as reg_count
        FROM users u 
        ORDER BY u.created_at DESC
    ''').fetchall()
    db.close()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<int:id>/change_role', methods=['POST'])
@role_required('admin')
def admin_change_role(id):
    new_role = request.form.get('role', 'attendee')
    if new_role not in ('admin', 'organizer', 'attendee'):
        flash('Invalid role selected.', 'error')
        return redirect(url_for('admin_users'))

    db = get_db()
    # Guard: prevent removing the last admin
    user = db.execute('SELECT * FROM users WHERE user_id = ?', (id,)).fetchone()
    if user and user['role'] == 'admin' and new_role != 'admin':
        admin_count = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin' AND is_active = 1").fetchone()['count']
        if admin_count <= 1:
            db.close()
            flash('Action denied: Cannot remove or demote the final administrator account.', 'error')
            return redirect(url_for('admin_users'))

    db.execute('UPDATE users SET role = ? WHERE user_id = ?', (new_role, id))
    db.commit()
    db.close()
    flash(f"User role updated to '{new_role}'.", 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:id>/toggle_status', methods=['POST'])
@role_required('admin')
def admin_toggle_user_status(id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE user_id = ?', (id,)).fetchone()
    if not user:
        db.close()
        flash('User not found.', 'error')
        return redirect(url_for('admin_users'))

    # Guard: prevent deactivating the last active admin
    if user['role'] == 'admin' and user['is_active']:
        admin_count = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin' AND is_active = 1").fetchone()['count']
        if admin_count <= 1:
            db.close()
            flash('Action denied: Cannot disable the final administrator account.', 'error')
            return redirect(url_for('admin_users'))

    new_status = 0 if user['is_active'] else 1
    db.execute('UPDATE users SET is_active = ? WHERE user_id = ?', (new_status, id))
    db.commit()
    db.close()
    flash(f"User account {'enabled' if new_status else 'disabled'} successfully.", 'info')
    return redirect(url_for('admin_users'))

@app.route('/admin/approvals')
@role_required('admin')
def admin_approvals():
    db = get_db()
    pending_events = db.execute('''
        SELECT e.*, u.name as organizer_name, u.email as organizer_email 
        FROM events e 
        LEFT JOIN users u ON e.organizer_id = u.user_id 
        WHERE e.status = 'PENDING_APPROVAL' 
        ORDER BY e.created_at ASC
    ''').fetchall()
    db.close()
    return render_template('admin/approvals.html', events=pending_events)

@app.route('/admin/event/<int:id>/approve', methods=['POST'])
@role_required('admin')
def admin_approve_event(id):
    db = get_db()
    event = db.execute('''
        SELECT e.*, u.name as org_name, u.email as org_email 
        FROM events e 
        LEFT JOIN users u ON e.organizer_id = u.user_id 
        WHERE e.event_id = ?
    ''', (id,)).fetchone()

    if not event:
        db.close()
        flash('Event not found.', 'error')
        return redirect(url_for('admin_approvals'))

    db.execute("UPDATE events SET status = 'PUBLISHED', rejection_reason = NULL WHERE event_id = ?", (id,))
    
    # Notify organizer
    if event['organizer_id']:
        create_notification(
            event['organizer_id'],
            "Event Approved!",
            f"Your event '{event['title']}' has been approved and is now live on the platform.",
            "success",
            link=url_for('event_detail', id=id),
            db=db
        )
        send_approval_status(event['org_email'], event['org_name'], event['title'], 'PUBLISHED')

    db.commit()
    db.close()
    flash(f"Event '{event['title']}' has been approved and published.", 'success')
    return redirect(url_for('admin_approvals'))

@app.route('/admin/event/<int:id>/reject', methods=['POST'])
@role_required('admin')
def admin_reject_event(id):
    reason = request.form.get('rejection_reason', 'Did not meet requirements').strip()
    db = get_db()
    event = db.execute('''
        SELECT e.*, u.name as org_name, u.email as org_email 
        FROM events e 
        LEFT JOIN users u ON e.organizer_id = u.user_id 
        WHERE e.event_id = ?
    ''', (id,)).fetchone()

    if not event:
        db.close()
        flash('Event not found.', 'error')
        return redirect(url_for('admin_approvals'))

    db.execute("UPDATE events SET status = 'REJECTED', rejection_reason = ? WHERE event_id = ?", (reason, id))
    
    if event['organizer_id']:
        create_notification(
            event['organizer_id'],
            "Event Needs Changes",
            f"Your event '{event['title']}' was rejected: {reason}",
            "danger",
            link=url_for('edit_event', id=id),
            db=db
        )
        send_approval_status(event['org_email'], event['org_name'], event['title'], 'REJECTED', reason)

    db.commit()
    db.close()
    flash(f"Event '{event['title']}' was rejected. Organizer notified.", 'info')
    return redirect(url_for('admin_approvals'))

@app.route('/admin/categories', methods=['GET', 'POST'])
@role_required('admin')
def admin_categories():
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        icon = request.form.get('icon', 'fa-folder').strip()

        if name:
            try:
                db.execute('INSERT INTO categories (name, description, icon) VALUES (?, ?, ?)',
                           (name, description, icon))
                db.commit()
                flash(f"Category '{name}' created successfully.", 'success')
            except sqlite3.IntegrityError:
                flash(f"Category '{name}' already exists.", 'error')

    categories = db.execute('''
        SELECT c.*, (SELECT COUNT(*) FROM events e WHERE e.category = c.name) as event_count 
        FROM categories c 
        ORDER BY c.name ASC
    ''').fetchall()
    db.close()
    return render_template('admin/categories.html', categories=categories)

@app.route('/admin/category/<int:id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_category(id):
    db = get_db()
    cat = db.execute('SELECT * FROM categories WHERE category_id = ?', (id,)).fetchone()
    if cat:
        db.execute('DELETE FROM categories WHERE category_id = ?', (id,))
        db.commit()
        flash(f"Category '{cat['name']}' removed.", 'info')
    db.close()
    return redirect(url_for('admin_categories'))

# -------------------------------------------------------------
# Analytics & Chart Data APIs
# -------------------------------------------------------------
@app.route('/admin/analytics')
@role_required('admin')
def admin_analytics():
    db = get_db()
    sync_event_lifecycle(db)

    # General KPIs
    total_events = db.execute('SELECT COUNT(*) as c FROM events').fetchone()['c']
    total_users = db.execute('SELECT COUNT(*) as c FROM users WHERE role != "admin"').fetchone()['c']
    total_regs = db.execute("SELECT COUNT(*) as c FROM registrations WHERE status != 'CANCELLED'").fetchone()['c']
    total_attended = db.execute("SELECT COUNT(*) as c FROM registrations WHERE status = 'ATTENDED'").fetchone()['c']
    attendance_rate = round((total_attended / total_regs * 100), 1) if total_regs > 0 else 0

    # Categorical breakdown
    cat_rows = db.execute('''
        SELECT category, COUNT(*) as cnt 
        FROM events 
        GROUP BY category
    ''').fetchall()

    # Status distribution
    status_rows = db.execute('''
        SELECT status, COUNT(*) as cnt 
        FROM events 
        GROUP BY status
    ''').fetchall()

    db.close()
    return render_template(
        'admin/analytics.html',
        kpis={
            'total_events': total_events,
            'total_users': total_users,
            'total_registrations': total_regs,
            'total_attendance': total_attended,
            'attendance_rate': attendance_rate
        },
        cat_data={r['category']: r['cnt'] for r in cat_rows},
        status_data={r['status']: r['cnt'] for r in status_rows}
    )

@app.route('/api/admin/analytics-data')
@role_required('admin')
def api_admin_analytics():
    db = get_db()
    cat_rows = db.execute('SELECT category, COUNT(*) as count FROM events GROUP BY category').fetchall()
    status_rows = db.execute('SELECT status, COUNT(*) as count FROM events GROUP BY status').fetchall()
    
    # Registrations by date (last 14 days)
    reg_rows = db.execute('''
        SELECT DATE(registration_date) as reg_day, COUNT(*) as count 
        FROM registrations 
        WHERE registration_date >= DATE('now', '-14 days')
        GROUP BY DATE(registration_date) 
        ORDER BY reg_day ASC
    ''').fetchall()

    db.close()
    return jsonify({
        'categories': {r['category']: r['count'] for r in cat_rows},
        'statuses': {r['status']: r['count'] for r in status_rows},
        'timeline': {r['reg_day']: r['count'] for r in reg_rows}
    })

# -------------------------------------------------------------
# CSV Report Exports
# -------------------------------------------------------------
@app.route('/admin/export/<report_type>.csv')
@role_required('admin')
def export_csv_report(report_type):
    db = get_db()
    output = io.StringIO()
    # Add UTF-8 BOM for Microsoft Excel compatibility
    output.write('\ufeff')
    writer = csv.writer(output)

    if report_type == 'users':
        writer.writerow(['User ID', 'Name', 'Email', 'Role', 'Status', 'Registered Date'])
        rows = db.execute('SELECT user_id, name, email, role, is_active, created_at FROM users').fetchall()
        for r in rows:
            writer.writerow([r['user_id'], r['name'], r['email'], r['role'], 'Active' if r['is_active'] else 'Disabled', r['created_at']])

    elif report_type == 'events':
        writer.writerow(['Event ID', 'Title', 'Category', 'Date', 'Time', 'Venue', 'Capacity', 'Registered', 'Price', 'Status'])
        rows = db.execute('SELECT event_id, title, category, date, time, venue, max_participants, current_participants, price, status FROM events').fetchall()
        for r in rows:
            writer.writerow([r['event_id'], r['title'], r['category'], r['date'], r['time'], r['venue'], r['max_participants'], r['current_participants'], r['price'], r['status']])

    elif report_type == 'registrations':
        writer.writerow(['Reg ID', 'Event Title', 'Attendee Name', 'Attendee Email', 'Ticket Code', 'Status', 'Payment Status', 'Reg Date'])
        rows = db.execute('''
            SELECT r.registration_id, e.title, u.name, u.email, r.ticket_code, r.status, r.payment_status, r.registration_date 
            FROM registrations r 
            JOIN events e ON r.event_id = e.event_id 
            JOIN users u ON r.user_id = u.user_id
        ''').fetchall()
        for r in rows:
            writer.writerow([r['registration_id'], r['title'], r['name'], r['email'], r['ticket_code'], r['status'], r['payment_status'], r['registration_date']])

    elif report_type == 'attendance':
        writer.writerow(['Ticket Code', 'Event Title', 'Attendee Name', 'Email', 'Checked In At'])
        rows = db.execute('''
            SELECT r.ticket_code, e.title, u.name, u.email, r.checked_in_at 
            FROM registrations r 
            JOIN events e ON r.event_id = e.event_id 
            JOIN users u ON r.user_id = u.user_id 
            WHERE r.status = 'ATTENDED'
        ''').fetchall()
        for r in rows:
            writer.writerow([r['ticket_code'], r['title'], r['name'], r['email'], r['checked_in_at']])
    else:
        db.close()
        abort(404)

    db.close()
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=eventorg_{report_type}.csv"}
    )

@app.route('/organizer/event/<int:id>/export-attendees.csv')
@role_required('organizer', 'admin')
def export_event_attendees(id):
    user_id = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()

    event = db.execute('SELECT * FROM events WHERE event_id = ?', (id,)).fetchone()
    if not event:
        db.close()
        abort(404)

    if not is_admin and event['organizer_id'] != user_id:
        db.close()
        abort(403)

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['Ticket Code', 'Attendee Name', 'Attendee Email', 'Registration Status', 'Payment Status', 'Registration Date', 'Checked In At'])

    rows = db.execute('''
        SELECT r.ticket_code, u.name, u.email, r.status, r.payment_status, r.registration_date, r.checked_in_at 
        FROM registrations r 
        JOIN users u ON r.user_id = u.user_id 
        WHERE r.event_id = ?
        ORDER BY r.registration_date ASC
    ''', (id,)).fetchall()

    for r in rows:
        writer.writerow([r['ticket_code'], r['name'], r['email'], r['status'], r['payment_status'], r['registration_date'], r['checked_in_at']])

    db.close()
    filename = f"attendees_event_{id}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# -------------------------------------------------------------
# Main Application Launcher
# -------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)
