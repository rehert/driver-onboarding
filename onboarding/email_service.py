import requests
from django.conf import settings


RESEND_ENDPOINT = "https://api.resend.com/emails"


def send_project_email(subject, message, recipient):
    """
    Send one transactional email through Resend over HTTPS.

    This avoids SMTP-port restrictions on the hosting service.
    The Resend API key is read from an environment variable through
    Django settings and is never stored in source code.
    """
    api_key = settings.RESEND_API_KEY

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured.")

    response = requests.post(
        RESEND_ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [recipient],
            "subject": subject,
            "text": message,
        },
        timeout=10,
    )

    if not response.ok:
        raise RuntimeError(
            f"Email provider returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    return True