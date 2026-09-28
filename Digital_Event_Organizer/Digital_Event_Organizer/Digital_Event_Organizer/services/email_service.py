import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger('EventOrgEmail')
logging.basicConfig(level=logging.INFO)

# Configuration from environment variables
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASS = os.getenv('SMTP_PASS', '')
MAIL_FROM = os.getenv('MAIL_FROM', 'noreply@eventorg.com')
MAIL_ENABLED = os.getenv('MAIL_ENABLED', 'False').lower() in ('true', '1', 't')

def send_email(to_email, subject, html_content, text_content=""):
    """
    Sends an email using configured SMTP server, or logs it cleanly if mail is disabled.
    Does not crash the application if credentials are not configured.
    """
    if not MAIL_ENABLED or not SMTP_USER or not SMTP_PASS:
        logger.info(f"[SIMULATED EMAIL] To: {to_email} | Subject: {subject}")
        logger.debug(f"[EMAIL BODY]: {text_content or html_content}")
        return True, "Email simulated successfully (MAIL_ENABLED is false or unconfigured)."

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = MAIL_FROM
        msg['To'] = to_email

        if text_content:
            msg.attach(MIMEText(text_content, 'plain'))
        if html_content:
            msg.attach(MIMEText(html_content, 'html'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        logger.info(f"[EMAIL SENT] Successfully sent email to {to_email}")
        return True, "Email sent successfully."
    except Exception as e:
        logger.error(f"[EMAIL ERROR] Failed to send email to {to_email}: {e}")
        return False, str(e)

def send_registration_confirmation(user_email, user_name, event_title, ticket_code, event_date, venue):
    subject = f"Registration Confirmed: {event_title} - EventOrg"
    html = f"""
    <div style="font-family: Outfit, sans-serif; background: #0f0c29; color: #ffffff; padding: 25px; border-radius: 12px;">
        <h2 style="color: #a29bfe;">Hello {user_name}!</h2>
        <p>Your registration for <strong>{event_title}</strong> has been confirmed.</p>
        <div style="background: rgba(255,255,255,0.08); padding: 15px; border-radius: 8px; margin: 20px 0;">
            <p><strong>Ticket ID:</strong> {ticket_code}</p>
            <p><strong>Date:</strong> {event_date}</p>
            <p><strong>Venue:</strong> {venue}</p>
        </div>
        <p>You can access your digital ticket and QR code anytime on your EventOrg Dashboard.</p>
        <p style="color: #888; font-size: 12px; margin-top: 30px;">EventOrg Platform &copy; 2026</p>
    </div>
    """
    text = f"Hello {user_name}!\nYour registration for {event_title} is confirmed.\nTicket ID: {ticket_code}\nDate: {event_date}\nVenue: {venue}"
    return send_email(user_email, subject, html, text)

def send_waitlist_promotion(user_email, user_name, event_title, ticket_code):
    subject = f"Good News! You have a seat for: {event_title} - EventOrg"
    html = f"""
    <div style="font-family: Outfit, sans-serif; background: #0f0c29; color: #ffffff; padding: 25px; border-radius: 12px;">
        <h2 style="color: #00cec9;">Great News, {user_name}!</h2>
        <p>A slot opened up and you have been promoted from the waitlist to <strong>CONFIRMED</strong> for <strong>{event_title}</strong>!</p>
        <div style="background: rgba(255,255,255,0.08); padding: 15px; border-radius: 8px; margin: 20px 0;">
            <p><strong>Ticket ID:</strong> {ticket_code}</p>
        </div>
        <p>Check your EventOrg Dashboard to view and download your digital ticket QR code.</p>
    </div>
    """
    text = f"Good News {user_name}!\nYou have been promoted from the waitlist for {event_title}.\nTicket ID: {ticket_code}"
    return send_email(user_email, subject, html, text)

def send_event_cancellation(user_email, user_name, event_title, reason=None):
    subject = f"Important Notice: {event_title} has been cancelled"
    reason_str = f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
    html = f"""
    <div style="font-family: Outfit, sans-serif; background: #0f0c29; color: #ffffff; padding: 25px; border-radius: 12px;">
        <h2 style="color: #ff7675;">Event Cancelled</h2>
        <p>Dear {user_name}, we regret to inform you that <strong>{event_title}</strong> has been cancelled.</p>
        {reason_str}
        <p>If this was a paid event, any eligible refunds will be processed automatically.</p>
    </div>
    """
    text = f"Dear {user_name},\n{event_title} has been cancelled. {reason or ''}"
    return send_email(user_email, subject, html, text)

def send_approval_status(organizer_email, organizer_name, event_title, status, reason=None):
    is_approved = status.upper() == 'PUBLISHED'
    subject = f"Event Submission {'Approved' if is_approved else 'Update'}: {event_title}"
    color = "#55efc4" if is_approved else "#ff7675"
    reason_html = f"<p><strong>Notes from Admin:</strong> {reason}</p>" if reason else ""
    html = f"""
    <div style="font-family: Outfit, sans-serif; background: #0f0c29; color: #ffffff; padding: 25px; border-radius: 12px;">
        <h2 style="color: {color};">Event Status: {status}</h2>
        <p>Dear {organizer_name}, your event <strong>{event_title}</strong> has been reviewed by the administration.</p>
        <p>Current Status: <strong>{status}</strong></p>
        {reason_html}
    </div>
    """
    text = f"Dear {organizer_name},\nYour event {event_title} status is now: {status}. {reason or ''}"
    return send_email(organizer_email, subject, html, text)
