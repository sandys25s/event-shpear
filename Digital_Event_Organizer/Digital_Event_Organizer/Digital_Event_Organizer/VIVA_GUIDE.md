# Digital Event Organizer (EventOrg) - Comprehensive Viva Voce Guide

## 1. Project Overview & Architecture
The **Digital Event Organizer (EventOrg)** is a production-grade, multi-role campus event management platform. It coordinates the full event lifecycle: drafting, administrative approval, multi-parameter search, real-time registration, waitlist queues with automated promotions, digital tickets with scannable QR codes, live attendance check-in, verified reviews, payment sandbox abstraction, and analytics.

### Key Architectural Pillars:
1. **Three-Tier Role-Based Access Control (RBAC)**:
   - **ADMIN**: Platform settings, category management, event approvals/rejections with feedback, user role assignment and activation controls, deep platform analytics, system-wide CSV reports.
   - **ORGANIZER**: Event authoring (17 fields), draft vs approval submission, participant management, live QR ticket scanning, attendance validation, and attendee CSV exports.
   - **ATTENDEE**: Multi-filter event discovery, seat booking, digital QR ticket wallet, waitlist queuing, cancellation with auto-slot handover, calendar synchronization (Google + .ICS), and post-event verified reviews.
2. **Event Finite State Machine (FSM)**:
   - `DRAFT` &rarr; `PENDING_APPROVAL` &rarr; `PUBLISHED` / `REJECTED` &rarr; `ONGOING` &rarr; `COMPLETED` / `CANCELLED` &rarr; `ARCHIVED`.
3. **Queue-Based Waitlist Engine**:
   - Automated FIFO promotion: when an active attendee cancels, the database immediately locates the earliest waitlisted participant, promotes them to `CONFIRMED`, generates a unique digital ticket with QR, and dispatches in-app and email notifications.
4. **QR Attendance Engine**:
   - Encodes JSON ticket payloads using Python's `qrcode` package. Verifiable via webcam/phone camera using `html5-qrcode` or manual ticket code lookup with guard rails against duplicate check-ins and mismatched events.

---

## 2. Technology Stack
- **Backend**: Python 3.14 + Flask 3.1
- **Database**: SQLite3 with foreign keys (`PRAGMA foreign_keys = ON`), indexed status queries, and transaction safety.
- **Frontend**: HTML5, CSS3 Custom Glassmorphism (`backdrop-filter: blur`), JavaScript ES6, Bootstrap 5.3, FontAwesome 6, Chart.js.
- **QR Code Generation**: Python `qrcode` and `Pillow`.
- **QR Code Scanning**: JavaScript `html5-qrcode` camera scanner.
- **Security**: Password hashing via `werkzeug.security` (scrypt / PBKDF2), role-based session decorators, input sanitization, and server-side validation.
- **Calendar Integration**: RFC 5545 compliant `.ics` generator and Google Calendar URL builder.
- **Email Service**: Dual-mode engine (`services/email_service.py`) supporting live SMTP and graceful fallback simulation logging when SMTP is unconfigured.
- **Payment Layer**: Architecture abstraction (`services/payment_service.py`) providing a realistic secure sandbox while prepared for Stripe/Razorpay integration.

---

## 3. Database Schema Overview
- `users`: `user_id`, `name`, `email`, `password`, `role` (`admin`, `organizer`, `attendee`), `is_active`, `created_at`
- `categories`: `category_id`, `name`, `description`, `icon`, `created_at`
- `events`: `event_id`, `organizer_id`, `title`, `description`, `date`, `time`, `end_time`, `venue`, `address`, `city`, `category`, `price`, `is_paid`, `max_participants`, `current_participants`, `deadline`, `image_url`, `contact_email`, `contact_phone`, `requirements`, `tags`, `status`, `rejection_reason`, `created_at`
- `registrations`: `registration_id`, `user_id`, `event_id`, `registration_date`, `status` (`CONFIRMED`, `WAITLISTED`, `ATTENDED`, `CANCELLED`, `NO_SHOW`), `payment_status`, `ticket_code`, `checked_in_at`
- `tickets`: `ticket_id`, `registration_id`, `ticket_code`, `event_id`, `user_id`, `qr_data`, `qr_path`, `status` (`VALID`, `USED`, `CANCELLED`), `issued_at`
- `notifications`: `notification_id`, `user_id`, `title`, `message`, `type`, `link`, `is_read`, `created_at`
- `reviews`: `review_id`, `event_id`, `user_id`, `rating` (1–5), `comment`, `created_at` (Unique per event/user)
- `payments`: `payment_id`, `registration_id`, `user_id`, `amount`, `transaction_id`, `payment_status`, `payment_date`

---

## 4. Key Viva Questions & Model Answers

**Q1: How does your role-based authorization work?**
*A: We enforce role-based access control at the server level using Python function decorators `@login_required` and `@role_required(*allowed_roles)`. Even if an attendee knows an admin or organizer URL, the server decorator verifies their session role and redirects them with an unauthorized alert.*

**Q2: How is the automatic waitlist promotion implemented?**
*A: When a user calls `/cancel_registration/<id>`, the cancellation endpoint runs within a database transaction: it updates the cancelling registration to `CANCELLED`, queries the `registrations` table for the earliest participant with `status = 'WAITLISTED'` on that event (`ORDER BY registration_id ASC LIMIT 1`), sets their status to `CONFIRMED`, issues their unique ticket code, generates their QR barcode, and notifies them via in-app alerts and email.*

**Q3: How do QR code check-ins prevent fraud or duplicate attendance?**
*A: The QR code encodes a verified payload containing the ticket code. When scanned at `/api/checkin/verify`, the backend validates that the ticket exists, matches the selected event, and inspects `checked_in_at` or `status == 'ATTENDED'`. If already scanned, it returns a 200 warning response with "⚠ Already Checked In at [Timestamp]" and refuses duplicate admission.*

**Q4: How does the platform ensure only verified attendees review an event?**
*A: Reviews are strictly guarded on `/event/<id>/review`: the server queries the `registrations` table for the requesting user and event. Only records where `status = 'ATTENDED'` (verified via physical QR check-in) are permitted to submit a 1-5 star review. A database unique constraint `UNIQUE(event_id, user_id)` guarantees one review per attendee.*

**Q5: How are analytics generated without hardcoding numbers?**
*A: Both the Admin Control Panel and `/api/admin/analytics-data` run real SQL aggregation queries: `COUNT(*)` with category grouping (`GROUP BY category`), status breakdown (`GROUP BY status`), and date truncation (`DATE(registration_date)` for 14-day velocity). Chart.js consumes these JSON endpoints to render dynamic Doughnut, Bar, and Line charts.*

**Q6: What safeguards protect the system against administrative lock-out?**
*A: In `admin_change_role` and `admin_toggle_user_status`, the backend executes a count query: `SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1`. If only one active admin remains, the system forbids demotion or deactivation and issues a flash warning: "Action denied: Cannot remove the final administrator account."*
