"""Create a test Stripe customer + active subscription.

Usage:
    python scripts/add_test_subscriber.py [email]

If no email is passed, you will be prompted.
Requires STRIPE_SECRET_KEY and STRIPE_PRICE_ID in .env.
Only use this in Stripe test mode (sk_test_...).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import stripe
from config.settings import STRIPE_SECRET_KEY
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")

if not STRIPE_SECRET_KEY:
    sys.exit("ERROR: STRIPE_SECRET_KEY not set in .env")
if not STRIPE_PRICE_ID:
    sys.exit("ERROR: STRIPE_PRICE_ID not set in .env")
if not STRIPE_SECRET_KEY.startswith("sk_test_"):
    sys.exit("ERROR: STRIPE_SECRET_KEY does not look like a test key (sk_test_...). "
             "Refusing to create fake subscribers in live mode.")

stripe.api_key = STRIPE_SECRET_KEY

email = sys.argv[1] if len(sys.argv) > 1 else input("Subscriber email: ").strip()
if not email:
    sys.exit("No email provided.")

print(f"\nCreating test subscriber: {email}")

# 1. Create or reuse customer
existing = stripe.Customer.list(email=email, limit=1).data
if existing:
    customer = existing[0]
    print(f"  Found existing customer: {customer.id}")
else:
    customer = stripe.Customer.create(email=email, name="Test Subscriber")
    print(f"  Created customer: {customer.id}")

# 2. Attach a test payment method (Visa, always succeeds)
pm = stripe.PaymentMethod.create(
    type="card",
    card={"token": "tok_visa"},
)
stripe.PaymentMethod.attach(pm.id, customer=customer.id)
stripe.Customer.modify(
    customer.id,
    invoice_settings={"default_payment_method": pm.id},
)
print(f"  Attached test card: {pm.id}")

# 3. Create subscription (or report if one already exists)
subs = stripe.Subscription.list(customer=customer.id, status="active", limit=10).data
active_on_price = [s for s in subs if any(i.price.id == STRIPE_PRICE_ID for i in s["items"].data)]
if active_on_price:
    print(f"  Subscription already active: {active_on_price[0].id}")
else:
    sub = stripe.Subscription.create(
        customer=customer.id,
        items=[{"price": STRIPE_PRICE_ID}],
        default_payment_method=pm.id,
    )
    print(f"  Created subscription: {sub.id}  status={sub.status}")

print("\nDone. Run POST /send-lesson to verify the email arrives.")
