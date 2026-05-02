import os
import logging

logger = logging.getLogger(__name__)

_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")


def is_twilio_configured() -> bool:
    return bool(_ACCOUNT_SID and _AUTH_TOKEN and _FROM_NUMBER)


def send_sms(to: str, body: str) -> dict:
    if not is_twilio_configured():
        logger.warning("Twilio not configured — SMS not sent. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.")
        return {"ok": False, "reason": "not_configured"}

    try:
        from twilio.rest import Client  # noqa: PLC0415
        client = Client(_ACCOUNT_SID, _AUTH_TOKEN)
        message = client.messages.create(body=body, from_=_FROM_NUMBER, to=to)
        return {"ok": True, "sid": message.sid}
    except ImportError:
        logger.warning("twilio package not installed — SMS not sent.")
        return {"ok": False, "reason": "package_not_installed"}
    except Exception as exc:
        logger.warning("Twilio send failed: %s", exc)
        return {"ok": False, "reason": str(exc)}
