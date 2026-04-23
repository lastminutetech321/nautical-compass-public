from fastapi import APIRouter

from modules.financial_engine.routes.open_account import open_account
from modules.financial_engine.routes.create_invoice import create_invoice
from modules.financial_engine.routes.payment_webhook import payment_webhook

financial_engine_actions_router = APIRouter()

@financial_engine_actions_router.get("/financial/action/check-mercury")
def check_mercury():
    return open_account()

@financial_engine_actions_router.get("/financial/action/create-invoice")
def create_invoice_action():
    return create_invoice()

@financial_engine_actions_router.get("/financial/action/record-payment")
def record_payment_action():
    return payment_webhook()
