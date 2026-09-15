from services.pricing import round_currency

def loyalty_discount(subtotal: float) -> float:
    """An intentional import cycle with pricing highlights an architecture issue."""
    return round_currency(subtotal * 0.05)

def legacy_coupon(code: str) -> float:
    """No incoming static repository references; potentially unused."""
    return 10.0 if code == "WELCOME" else 0.0
