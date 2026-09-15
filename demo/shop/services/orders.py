from models.database import get_session
from models.entities import Order
from services.users import UserService
from services.payments import PaymentService
from services.pricing import calculate_total
from services.audit import record_event

class OrderService:
    """Coordinate customer validation, pricing, payment, and order persistence."""
    @staticmethod
    def checkout(user_id: int, items: list, payment_method: str):
        user = UserService.get_user(user_id)
        total = calculate_total(items)
        PaymentService.process_payment(total, payment_method)
        session = get_session()
        session.add(Order(user_id=user.id, total=total, status="paid"))
        session.commit()
        record_event("order.created", user.id)
        return {"status": "paid", "total": total}

    @staticmethod
    def list_orders(user_id: int):
        session = get_session()
        return session.query(Order).filter_by(user_id=user_id).all()
