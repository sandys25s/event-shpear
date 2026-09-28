import os
import secrets
import io
import base64
import json
import qrcode

QR_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads', 'qrcodes')

def ensure_qr_dir():
    if not os.path.exists(QR_STORAGE_DIR):
        os.makedirs(QR_STORAGE_DIR, exist_ok=True)

def generate_ticket_code(event_id, user_id):
    """
    Generates a unique, readable ticket code.
    Example: TKT-104-E2A9B8
    """
    rand_suffix = secrets.token_hex(3).upper()
    return f"TKT-{event_id:03d}-{user_id:03d}-{rand_suffix}"

def generate_qr_image(ticket_code, event_id, user_id):
    """
    Generates QR code for a ticket and returns:
    1. qr_data string
    2. base64 data URI for direct inline rendering
    3. relative web path to static file
    """
    ensure_qr_dir()
    
    # Payload encoded in QR
    payload = {
        "ticket_code": ticket_code,
        "event_id": event_id,
        "user_id": user_id
    }
    qr_data = json.dumps(payload)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1f2421", back_color="#ffffff")

    # Save to file
    filename = f"{ticket_code}.png"
    filepath = os.path.join(QR_STORAGE_DIR, filename)
    img.save(filepath)
    rel_path = f"/static/uploads/qrcodes/{filename}"

    # Also generate base64 URI
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    b64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    data_uri = f"data:image/png;base64,{b64_str}"

    return qr_data, data_uri, rel_path
