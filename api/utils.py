import base64
import io
import secrets
from django.utils import timezone
from rest_framework.response import Response
from rest_framework import status

import qrcode
from operations.models import Notification, GuestVisit, IDTag, IDTagIssue


def api_response(success=True, message="", data=None, errors=None, status_code=status.HTTP_200_OK):
    """
    Standard JSON envelope for all Mobiz API responses.
    Success: {"success": True, "message": "...", "data": {...}}
    Error:   {"success": False, "message": "...", "errors": {...}}
    """
    payload = {
        "success": bool(success),
        "message": message,
    }
    if success:
        payload["data"] = data if data is not None else {}
    else:
        payload["errors"] = errors if errors is not None else {}
    return Response(payload, status=status_code)


def generate_gate_pass_code():
    """
    Generates a unique Gate Pass / Entry code in format ENT-YYYYMMDD-XXXXXX.
    """
    for _ in range(20):
        suffix = secrets.token_hex(3).upper()
        code = f"ENT-{timezone.localdate():%Y%m%d}-{suffix}"
        if not GuestVisit.objects.filter(gate_pass_code=code).exists():
            return code
    # Fallback with longer entropy if necessary
    return f"ENT-{timezone.localdate():%Y%m%d}-{secrets.token_hex(6).upper()}"


def generate_qr_code_base64(data_string):
    """
    Generates a base64 encoded PNG data URI for the given string.
    """
    if not data_string:
        return ""
    try:
        qr = qrcode.QRCode(version=1, box_size=6, border=3)
        qr.add_data(data_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""


def mask_id_number(raw_id):
    """
    Masks sensitive ID numbers, showing only the last 4 characters.
    """
    raw_id = (raw_id or "").strip()
    if not raw_id:
        return ""
    if len(raw_id) <= 4:
        return raw_id
    return ("*" * (len(raw_id) - 4)) + raw_id[-4:]


def create_notification(recipient, title, message, notification_type, visit=None, sender=None):
    """
    Helper to create an in-app notification for a user.
    """
    if not recipient:
        return None
    try:
        return Notification.objects.create(
            recipient=recipient,
            sender=sender,
            visit=visit,
            title=title,
            message=message,
            notification_type=notification_type,
        )
    except Exception:
        return None
