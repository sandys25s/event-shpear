# Digital Event Organizer (EventOrg) - Production Test Cases

| TC ID | Module | Test Scenario | Steps to Perform | Expected Result | Status |
|-------|--------|---------------|------------------|-----------------|--------|
| TC_01 | Auth | User Registration | 1. Navigate to `/register`<br>2. Select Role (Attendee / Organizer)<br>3. Submit valid form | Account created in DB with hashed password; redirected to login. | PASSED |
| TC_02 | Auth | Admin Login & Routing | 1. Enter `admin@event.com` / `admin123`<br>2. Submit | Logged in with admin session; redirected to Admin Control Panel. | PASSED |
| TC_03 | Auth | Organizer Login & Routing | 1. Enter `organizer@event.com` / `organizer123`<br>2. Submit | Logged in with organizer session; redirected to Organizer Workspace. | PASSED |
| TC_04 | Auth | Attendee Login & Routing | 1. Enter `attendee@event.com` / `user123`<br>2. Submit | Logged in with attendee session; redirected to Attendee Dashboard. | PASSED |
| TC_05 | Admin | Live Statistics & Real DB Data | 1. Open `/admin/dashboard`<br>2. Inspect Event, User, Registration counts | Statistic cards display live DB numbers, not hardcoded strings. | PASSED |
| TC_06 | Admin | Chart.js Analytics | 1. Open `/admin/dashboard` & `/admin/analytics`<br>2. Inspect category & trend charts | Category breakdown and 14-day timeline render dynamically from `/api/admin/analytics-data`. | PASSED |
| TC_07 | Admin | User Role Reassignment | 1. Open `/admin/users`<br>2. Change user role via dropdown | Role updated in DB and reflects on user's next session. | PASSED |
| TC_08 | Security | Last Admin Protection Guard | 1. Attempt to demote or disable final active admin account | System blocks action with explicit flash error "Action denied: Cannot remove final admin". | PASSED |
| TC_09 | Organizer | Event Creation (Save Draft) | 1. Open `/organizer/create_event`<br>2. Enter details & click "Save as Draft" | Event saved in DB with status `DRAFT`; does not show on public Explore. | PASSED |
| TC_10 | Organizer | Submit Event for Approval | 1. Fill event form & click "Submit for Approval" | Status set to `PENDING_APPROVAL`; notification dispatched to admin queue. | PASSED |
| TC_11 | Admin | Event Approval Workflow | 1. Open `/admin/approvals`<br>2. Click "Approve" on pending event | Event status updated to `PUBLISHED`; organizer receives notification and email. | PASSED |
| TC_12 | Admin | Event Rejection with Reason | 1. Click "Reject" on pending event<br>2. Provide constructive rejection reason<br>3. Submit | Event status updated to `REJECTED`; rejection reason recorded and sent to organizer. | PASSED |
| TC_13 | Attendee | Explore Multi-Filter Search | 1. Open `/events`<br>2. Filter by keyword, category, date, price, availability | Instant client-side + server-side filtering updates list accurately. | PASSED |
| TC_14 | Attendee | Free Registration & Ticket QR | 1. Register for published free event<br>2. View ticket confirmation | Registration confirmed, unique ticket ID generated, QR code image rendered. | PASSED |
| TC_15 | Attendee | Duplicate Registration Prevention | 1. Attempt to register for the same event a second time | System detects existing registration and alerts user without double-booking. | PASSED |
| TC_16 | Waitlist | Capacity Enforcement & Waitlist | 1. Max participants reached (e.g. 1/1)<br>2. Another attendee clicks Register | System displays "Event Full" and places user on `WAITLISTED` status. | PASSED |
| TC_17 | Waitlist | Automatic Waitlist Promotion | 1. Confirmed attendee cancels booking<br>2. System executes cancellation | First waitlisted attendee is automatically promoted to `CONFIRMED`, ticket QR is generated, and email notification sent. | PASSED |
| TC_18 | Check-In | Live QR Ticket Verification | 1. Open `/organizer/checkin`<br>2. Scan or enter attendee ticket ID | Returns "✓ Check-in Successful", marks status `ATTENDED`, and records check-in timestamp. | PASSED |
| TC_19 | Check-In | Duplicate Check-In Guard | 1. Scan the same ticket ID a second time | Returns "⚠ Already Checked In at [Timestamp]" and prevents duplicate attendance count. | PASSED |
| TC_20 | Check-In | Mismatched Event Guard | 1. Scan ticket with mismatched event selected | Returns error indicating ticket belongs to another event. | PASSED |
| TC_21 | Reviews | Verified Attendee Review | 1. Attendee marked `ATTENDED` opens completed event<br>2. Submits 1-5 star review & comment | Review accepted and average star rating updates on event page. | PASSED |
| TC_22 | Reviews | Non-Attendee Review Prevention | 1. User who has not attended tries to post review | Access blocked; message explains only verified attendees can review. | PASSED |
| TC_23 | Calendar | Google Calendar & .ICS Sync | 1. Click "Google Calendar" or ".ICS File" | Google Calendar opens pre-filled URL; .ICS downloads standard RFC 5545 calendar file. | PASSED |
| TC_24 | Reports | Admin & Organizer CSV Exports | 1. Export Users / Events / Registrations / Attendance CSVs | Clean UTF-8 CSV downloaded with appropriate headers and data. | PASSED |
| TC_25 | Payments | Realistic Payment Sandbox | 1. Select paid event & proceed to checkout<br>2. Submit Card / UPI payment | Payment processed, transaction ID recorded in `payments` table, confirmed ticket issued. | PASSED |
| TC_26 | Security | Route Authorization Checks | 1. Attendee visits `/admin/dashboard` or `/organizer/dashboard` | Access blocked by `@role_required` decorator with proper unauthorized redirect. | PASSED |
