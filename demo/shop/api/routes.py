from fastapi import FastAPI, Depends
from api.middleware import require_user
from services.auth import AuthService
from services.orders import OrderService
from services.users import UserService

app = FastAPI(title="Northstar Commerce")

@app.post("/login")
def login(email: str, password: str):
    return AuthService.login(email, password)

@app.post("/users")
def register(email: str, password: str):
    return UserService.register(email, password)

@app.get("/profile")
def profile(user=Depends(require_user)):
    return UserService.get_user(user.id)

@app.post("/checkout")
def checkout(items: list, payment_method: str, user=Depends(require_user)):
    return OrderService.checkout(user.id, items, payment_method)

@app.get("/orders")
def orders(user=Depends(require_user)):
    return OrderService.list_orders(user.id)
