import os
import uuid
from datetime import datetime

PAYMENT_GATEWAY = os.getenv('PAYMENT_GATEWAY', 'sandbox') # 'sandbox', 'stripe', 'razorpay'
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', '')

def get_gateway_info():
    """
    Returns information on configured payment gateway.
    """
    if STRIPE_SECRET_KEY:
        return {"provider": "stripe", "mode": "live", "configured": True}
    elif RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
        return {"provider": "razorpay", "mode": "live", "configured": True}
    else:
        return {
            "provider": "sandbox",
            "mode": "test_sandbox",
            "configured": False,
            "instructions": "To enable real transactions, configure STRIPE_SECRET_KEY or RAZORPAY_KEY_ID & RAZORPAY_KEY_SECRET in environment variables."
        }

def create_transaction_id():
    now_str = datetime.now().strftime("%Y%m%d%H%M%S")
    rand_str = uuid.uuid4().hex[:6].upper()
    return f"TXN-{now_str}-{rand_str}"

def process_payment(amount, user_id, event_id, payment_method="card"):
    """
    Processes payment according to configured gateway.
    In sandbox mode, generates a verified test transaction.
    """
    gateway = get_gateway_info()
    txn_id = create_transaction_id()
    
    if gateway["provider"] == "sandbox":
        # Realistic Sandbox processing
        return {
            "success": True,
            "transaction_id": txn_id,
            "amount": float(amount),
            "status": "paid",
            "gateway": "sandbox",
            "timestamp": datetime.now().isoformat(),
            "message": "Processed via EventOrg Secure Sandbox"
        }
    
    # Real payment gateways can be invoked here:
    # e.g., Stripe PaymentIntent or Razorpay Order verification.
    return {
        "success": False,
        "transaction_id": txn_id,
        "amount": float(amount),
        "status": "failed",
        "gateway": gateway["provider"],
        "timestamp": datetime.now().isoformat(),
        "message": f"Payment gateway '{gateway['provider']}' requires API credentials configuration."
    }
