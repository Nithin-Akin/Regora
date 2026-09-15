from services.provider import StripeClient
from services.audit import record_event

class PaymentService:
    """Charge a payment method through the external payment provider."""
    @staticmethod
    def process_payment(total: float, payment_method: str):
        receipt = StripeClient.charge(total, payment_method)
        record_event("payment.completed", receipt["id"])
        return receipt
