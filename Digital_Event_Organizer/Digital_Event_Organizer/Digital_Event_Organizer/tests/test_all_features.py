import os
import sys
import unittest
import json
import uuid

# Add app root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, get_db

class EventOrgProductionTestSuite(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key'
        self.client = app.test_client()

    def test_01_public_pages(self):
        """Verify home and explore pages load with 200 OK and render correctly."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'EventOrg', res.data)

        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Explore', res.data)

    def test_02_three_roles_login(self):
        """Verify all 3 roles: admin, organizer, attendee can log in."""
        # 1. Admin login
        res = self.client.post('/login', data={'email': 'admin@event.com', 'password': 'admin123'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Admin', res.data)

        # 2. Organizer login
        res = self.client.post('/login', data={'email': 'organizer@event.com', 'password': 'organizer123'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Organizer', res.data)

        # 3. Attendee login
        res = self.client.post('/login', data={'email': 'attendee@event.com', 'password': 'user123'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dashboard', res.data)

    def test_03_admin_dashboard_metrics(self):
        """Verify Admin Control panel returns real counts from DB and no template errors."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['name'] = 'Admin User'
            sess['email'] = 'admin@event.com'
            sess['role'] = 'admin'

        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Total Events', res.data)
        self.assertIn(b'Platform Users', res.data)
        self.assertIn(b'Registrations', res.data)

        # Analytics API
        api_res = self.client.get('/api/admin/analytics-data')
        self.assertEqual(api_res.status_code, 200)
        data = json.loads(api_res.data)
        self.assertIn('categories', data)
        self.assertIn('statuses', data)

    def test_04_admin_user_management_and_guards(self):
        """Verify user listing, role switching, and guard against removing last admin."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['name'] = 'Admin User'
            sess['email'] = 'admin@event.com'
            sess['role'] = 'admin'

        # User list
        res = self.client.get('/admin/users')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'admin@event.com', res.data)

        # Try to demote last active admin
        res = self.client.post('/admin/user/1/change_role', data={'role': 'attendee'}, follow_redirects=True)
        self.assertIn(b'Action denied', res.data)

    def test_05_event_lifecycle_approval_workflow(self):
        """Test complete workflow: Organizer creates event -> Pending -> Admin approves -> Published."""
        unique_title = f"Lifecycle Symposium {uuid.uuid4().hex[:6]}"
        
        # 1. Organizer creates event
        with self.client.session_transaction() as sess:
            sess['user_id'] = 3
            sess['name'] = 'Prof. Ramesh Organizer'
            sess['email'] = 'organizer@event.com'
            sess['role'] = 'organizer'

        event_data = {
            'title': unique_title,
            'description': 'A fully automated test event description.',
            'category': 'Tech',
            'date': '2026-11-20',
            'time': '10:00',
            'end_time': '16:00',
            'venue': 'Test Hall 101',
            'city': 'Coimbatore',
            'max_participants': 25,
            'deadline': '2026-11-19 23:59:00',
            'action': 'submit'
        }
        res = self.client.post('/organizer/create_event', data=event_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Verify event was inserted as PENDING_APPROVAL
        db = get_db()
        ev = db.execute("SELECT * FROM events WHERE title = ?", (unique_title,)).fetchone()
        self.assertIsNotNone(ev)
        ev_id = ev['event_id']
        self.assertEqual(ev['status'], 'PENDING_APPROVAL')
        db.close()

        # 2. Admin reviews approvals
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['name'] = 'Admin User'
            sess['role'] = 'admin'

        appr_page = self.client.get('/admin/approvals')
        self.assertEqual(appr_page.status_code, 200)
        self.assertIn(unique_title.encode('utf-8'), appr_page.data)

        # 3. Admin approves
        approve_res = self.client.post(f'/admin/event/{ev_id}/approve', follow_redirects=True)
        self.assertEqual(approve_res.status_code, 200)

        db = get_db()
        ev_after = db.execute("SELECT status FROM events WHERE event_id = ?", (ev_id,)).fetchone()
        self.assertEqual(ev_after['status'], 'PUBLISHED')
        db.close()

    def test_06_capacity_waitlist_and_autopromotion(self):
        """Test event capacity limit (1 seat), waitlist insertion, and auto-promotion upon cancellation."""
        unique_title = f"Waitlist Test {uuid.uuid4().hex[:6]}"
        db = get_db()
        cursor = db.execute('''
            INSERT INTO events (
                organizer_id, title, description, category, date, time, venue,
                max_participants, current_participants, deadline, status, is_paid
            ) VALUES (3, ?, 'Testing waitlist functionality.', 'Seminar', '2026-12-10', '09:00', 'Room A', 1, 0, '2026-12-09 23:59:00', 'PUBLISHED', 0)
        ''', (unique_title,))
        test_ev_id = cursor.lastrowid
        db.commit()
        db.close()

        # 1. Attendee 1 (User 2) registers -> Confirmed
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['name'] = 'Santhosh Kumar'
            sess['email'] = 'user@event.com'
            sess['role'] = 'attendee'

        res1 = self.client.post(f'/register_event/{test_ev_id}', follow_redirects=True)
        self.assertEqual(res1.status_code, 200)

        db = get_db()
        ev = db.execute("SELECT current_participants FROM events WHERE event_id = ?", (test_ev_id,)).fetchone()
        self.assertEqual(ev['current_participants'], 1)
        reg1 = db.execute("SELECT * FROM registrations WHERE event_id = ? AND user_id = 2", (test_ev_id,)).fetchone()
        self.assertEqual(reg1['status'], 'CONFIRMED')
        self.assertIsNotNone(reg1['ticket_code'])
        db.close()

        # 2. Attendee 2 (User 4) registers -> Capacity full -> Placed on Waitlist
        with self.client.session_transaction() as sess:
            sess['user_id'] = 4
            sess['name'] = 'Priya Sharma'
            sess['email'] = 'attendee@event.com'
            sess['role'] = 'attendee'

        res2 = self.client.post(f'/register_event/{test_ev_id}', follow_redirects=True)
        self.assertEqual(res2.status_code, 200)

        db = get_db()
        reg2 = db.execute("SELECT * FROM registrations WHERE event_id = ? AND user_id = 4", (test_ev_id,)).fetchone()
        self.assertEqual(reg2['status'], 'WAITLISTED')
        db.close()

        # 3. Attendee 1 cancels registration -> Attendee 2 must be automatically promoted!
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['role'] = 'attendee'

        cancel_res = self.client.post(f'/cancel_registration/{reg1["registration_id"]}', follow_redirects=True)
        self.assertEqual(cancel_res.status_code, 200)

        db = get_db()
        reg1_after = db.execute("SELECT status FROM registrations WHERE registration_id = ?", (reg1['registration_id'],)).fetchone()
        self.assertEqual(reg1_after['status'], 'CANCELLED')

        reg2_promoted = db.execute("SELECT * FROM registrations WHERE registration_id = ?", (reg2['registration_id'],)).fetchone()
        self.assertEqual(reg2_promoted['status'], 'CONFIRMED')
        self.assertIsNotNone(reg2_promoted['ticket_code'])

        # Verify ticket was generated for promoted attendee
        ticket = db.execute("SELECT * FROM tickets WHERE registration_id = ?", (reg2['registration_id'],)).fetchone()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket['status'], 'VALID')

        # Current participants must still be 1 (promoted filled the slot)
        ev_after = db.execute("SELECT current_participants FROM events WHERE event_id = ?", (test_ev_id,)).fetchone()
        self.assertEqual(ev_after['current_participants'], 1)
        db.close()

    def test_07_qr_checkin_flow(self):
        """Test QR check-in API: valid checkin, duplicate checkin detection, invalid code handling."""
        # Create a fresh event and confirmed ticket specifically for checkin test
        db = get_db()
        cur = db.execute('''
            INSERT INTO events (organizer_id, title, description, category, date, time, venue, max_participants, deadline, status)
            VALUES (1, 'Scan Checkin Test Event', 'Desc', 'Tech', '2026-12-15', '10:00', 'Hall 1', 50, '2026-12-14 23:59:00', 'PUBLISHED')
        ''')
        chk_ev_id = cur.lastrowid
        from services.ticket_service import generate_ticket_code, generate_qr_image
        code = generate_ticket_code(chk_ev_id, 2)
        qr_data, qr_uri, qr_path = generate_qr_image(code, chk_ev_id, 2)
        cur = db.execute('''
            INSERT INTO registrations (user_id, event_id, status, payment_status, ticket_code)
            VALUES (2, ?, 'CONFIRMED', 'paid', ?)
        ''', (chk_ev_id, code))
        reg_id = cur.lastrowid
        db.execute('''
            INSERT INTO tickets (registration_id, ticket_code, event_id, user_id, qr_data, qr_path, status)
            VALUES (?, ?, ?, 2, ?, ?, 'VALID')
        ''', (reg_id, code, chk_ev_id, qr_data, qr_path))
        db.commit()
        db.close()

        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['name'] = 'Admin User'
            sess['role'] = 'admin'

        # 1. First scan -> Success
        scan_res1 = self.client.post('/api/checkin/verify', json={'ticket_code': code, 'event_id': chk_ev_id})
        self.assertEqual(scan_res1.status_code, 200)
        data1 = json.loads(scan_res1.data)
        self.assertTrue(data1['success'])
        self.assertIn('Check-in Successful', data1['message'])

        # 2. Duplicate scan -> Already Checked In
        scan_res2 = self.client.post('/api/checkin/verify', json={'ticket_code': code})
        self.assertEqual(scan_res2.status_code, 200)
        data2 = json.loads(scan_res2.data)
        self.assertFalse(data2['success'])
        self.assertTrue(data2.get('already_checked_in', False))
        self.assertIn('Already Checked In', data2['message'])

        # 3. Invalid ticket code -> 404
        scan_res3 = self.client.post('/api/checkin/verify', json={'ticket_code': 'INVALID-CODE-999'})
        self.assertEqual(scan_res3.status_code, 404)

    def test_08_calendar_and_csv_exports(self):
        """Verify .ics calendar generation and CSV report downloads."""
        # Calendar .ics
        cal_res = self.client.get('/event/1/calendar.ics')
        self.assertEqual(cal_res.status_code, 200)
        self.assertIn(b'BEGIN:VCALENDAR', cal_res.data)
        self.assertIn(b'END:VCALENDAR', cal_res.data)

        # Admin CSV exports
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'admin'

        for rpt in ['users', 'events', 'registrations', 'attendance']:
            csv_res = self.client.get(f'/admin/export/{rpt}.csv')
            self.assertEqual(csv_res.status_code, 200)
            self.assertIn('text/csv', csv_res.headers['Content-Type'])

    def test_09_reviews_and_security(self):
        """Test event reviews (only attended users) and role-based route security."""
        # 1. Non-attended user tries to review -> Rejected
        with self.client.session_transaction() as sess:
            sess['user_id'] = 4
            sess['role'] = 'attendee'

        rev_res1 = self.client.post('/event/1/review', data={'rating': 5, 'comment': 'Great event!'}, follow_redirects=True)
        self.assertIn(b'Only verified attendees', rev_res1.data)

        # 2. Unauthorized attendee tries to access admin panel -> Blocked
        admin_res = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertIn(b'Unauthorized access', admin_res.data)

    def test_10_paid_event_registration_flow(self):
        """Test paid event checkout and transaction record generation."""
        # Create a paid event
        db = get_db()
        cur = db.execute('''
            INSERT INTO events (
                organizer_id, title, description, category, date, time, venue,
                max_participants, current_participants, deadline, status, is_paid, price
            ) VALUES (1, 'Paid Masterclass', 'Paid event testing.', 'Workshop', '2026-12-28', '14:00', 'Lab 2', 50, 0, '2026-12-27 23:59:00', 'PUBLISHED', 1, 299.00)
        ''')
        paid_ev_id = cur.lastrowid
        db.commit()
        db.close()

        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['name'] = 'Santhosh Kumar'
            sess['email'] = 'user@event.com'
            sess['role'] = 'attendee'

        # Initial register on paid event redirects to payment
        reg_res = self.client.post(f'/register_event/{paid_ev_id}')
        self.assertEqual(reg_res.status_code, 302)
        self.assertIn(f'/payment/{paid_ev_id}', reg_res.headers['Location'])

        # Checkout via payment route
        pay_res = self.client.post(f'/payment/{paid_ev_id}', data={'payment_method': 'card'}, follow_redirects=True)
        self.assertEqual(pay_res.status_code, 200)
        self.assertIn(b'Payment successful', pay_res.data)

        # Verify payment record in DB
        db = get_db()
        payment = db.execute("SELECT * FROM payments WHERE user_id = 2 ORDER BY payment_id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(payment)
        self.assertEqual(payment['amount'], 299.00)
        self.assertEqual(payment['payment_status'], 'paid')
        db.close()

    def test_11_admin_dashboard_ui_layout_and_elements(self):
        """Verify Admin Control panel UI layout, chart containers, loading overlays, and pills."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['name'] = 'Admin User'
            sess['email'] = 'admin@event.com'
            sess['role'] = 'admin'

        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 200)
        content = res.data.decode('utf-8')

        # Check containers and loading states
        self.assertIn('id="categoryChartContainer"', content)
        self.assertIn('id="catChartLoading"', content)
        self.assertIn('id="trendChartContainer"', content)
        self.assertIn('id="trendChartLoading"', content)

        # Check flex containment
        self.assertIn('d-flex flex-column', content)
        self.assertIn('position-absolute top-0 start-0 w-100 h-100', content)
        self.assertIn('mt-auto pt-3 border-top', content)

        # Check Chart.js script cleans up loading
        self.assertIn('catLoading.remove()', content)
        self.assertIn('trendLoading.remove()', content)

if __name__ == '__main__':
    unittest.main()

