from fastapi import APIRouter

from modules.financial_engine.routes.open_account import open_account
from modules.financial_engine.routes.create_invoice import create_invoice
from modules.financial_engine.routes.payment_webhook import payment_webhook

financial_engine_router = APIRouter()

@financial_engine_router.get("/financial/test")
def financial_test():
    return {
        "account": open_account(),
        "invoice": create_invoice(),
        "payment": payment_webhook()
    }
