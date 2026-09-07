import os
import smtplib
from email.message import EmailMessage


def mail_enabled() -> bool:
    return bool(
        os.environ.get("MAIL_SERVER")
        and os.environ.get("MAIL_USERNAME")
        and os.environ.get("MAIL_PASSWORD")
    )


def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("MAIL_DEFAULT_SENDER", os.environ["MAIL_USERNAME"])
    msg["To"] = to
    msg.set_content(body)

    port = int(os.environ.get("MAIL_PORT", "587"))
    use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() != "false"

    with smtplib.SMTP(os.environ["MAIL_SERVER"], port, timeout=10) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
        smtp.send_message(msg)
