from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from modules.financial_engine.routes.open_account import open_account
from modules.financial_engine.routes.create_invoice import create_invoice
from modules.financial_engine.routes.payment_webhook import payment_webhook

financial_engine_panel_router = APIRouter()

@financial_engine_panel_router.get("/financial/panel", response_class=HTMLResponse)
def financial_panel():
    account = open_account()
    invoice = create_invoice()
    payment = payment_webhook()

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Financial Engine Panel</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #0b1020;
                color: #f5f7fb;
                margin: 0;
                padding: 24px;
            }}
            .wrap {{
                max-width: 1100px;
                margin: 0 auto;
            }}
            h1 {{
                margin: 0 0 8px 0;
                font-size: 32px;
            }}
            p.sub {{
                margin: 0 0 24px 0;
                color: #aab4c8;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
                gap: 18px;
            }}
            .card {{
                background: #121933;
                border: 1px solid #263252;
                border-radius: 16px;
                padding: 20px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.25);
            }}
            .label {{
                font-size: 13px;
                text-transform: uppercase;
                color: #8ea0c9;
                letter-spacing: 0.08em;
                margin-bottom: 10px;
            }}
            .value {{
                font-size: 24px;
                font-weight: 700;
                margin-bottom: 8px;
            }}
            .meta {{
                color: #c8d2e6;
                font-size: 14px;
                line-height: 1.6;
            }}
            .ok {{
                color: #7ee787;
            }}
            .warn {{
                color: #ffcc66;
            }}
            .row {{
                margin-top: 28px;
                background: #121933;
                border: 1px solid #263252;
                border-radius: 16px;
                padding: 20px;
            }}
            code {{
                display: block;
                white-space: pre-wrap;
                word-break: break-word;
                background: #0d1429;
                border: 1px solid #24314f;
                color: #d9e2f2;
                padding: 14px;
                border-radius: 12px;
                margin-top: 12px;
                font-size: 13px;
            }}
            .badge {{
                display: inline-block;
                padding: 6px 10px;
                border-radius: 999px;
                font-size: 12px;
                font-weight: 700;
                background: #1c2645;
                color: #dbe6ff;
                margin-top: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="wrap">
            <h1>Financial Engine Panel</h1>
            <p class="sub">Live starter panel for Mercury, invoicing, and payment flow.</p>

            <div class="grid">
                <div class="card">
                    <div class="label">Mercury Connection</div>
                    <div class="value {'warn' if account.get('status') == 'not_configured' else 'ok'}">{account.get('status')}</div>
                    <div class="meta">
                        Provider: {account.get('provider')}<br/>
                        Business ID: {account.get('business_id')}<br/>
                        Message: {account.get('message')}
                    </div>
                    <div class="badge">Base URL: {account.get('integration', {}).get('base_url', 'n/a')}</div>
                </div>

                <div class="card">
                    <div class="label">Invoice Flow</div>
                    <div class="value ok">{invoice.get('status')}</div>
                    <div class="meta">
                        Customer ID: {invoice.get('customer_id')}<br/>
                        Amount: {invoice.get('amount')}<br/>
                        Message: {invoice.get('message')}
                    </div>
                </div>

                <div class="card">
                    <div class="label">Payment Flow</div>
                    <div class="value ok">{payment.get('status')}</div>
                    <div class="meta">
                        Invoice ID: {payment.get('invoice_id')}<br/>
                        Amount: {payment.get('amount')}<br/>
                        Provider: {payment.get('provider')}<br/>
                        Message: {payment.get('message')}
                    </div>
                </div>
            </div>

            <div class="row">
                <div class="label">Raw Account Response</div>
                <code>{account}</code>
            </div>

            <div class="row">
                <div class="label">Raw Invoice Response</div>
                <code>{invoice}</code>
            </div>

            <div class="row">
                <div class="label">Raw Payment Response</div>
                <code>{payment}</code>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
