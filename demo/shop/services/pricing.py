from services.discounts import loyalty_discount

def calculate_total(items: list) -> float:
    """Price a basket after applying the customer's loyalty discount."""
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    return subtotal - loyalty_discount(subtotal)

def round_currency(amount: float) -> float:
    return round(amount, 2)
