import os
import stripe

class StripeClient:
    """Boundary for outbound Stripe payment requests."""
    @staticmethod
    def charge(total: float, payment_method: str):
        stripe.api_key = os.environ["STRIPE_API_KEY"]
        return stripe.PaymentIntent.create(amount=int(total * 100), currency="usd", payment_method=payment_method, confirm=True)
