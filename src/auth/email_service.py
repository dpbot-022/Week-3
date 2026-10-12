import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, formatdate
from typing import Optional
from jinja2 import Template
import aiosmtplib

from src.core.config import settings
from src.core.logging import logger

class SMTPConfigurationError(Exception):
    """Raised when SMTP is improperly configured in production."""
    pass

class SMTPDeliveryError(Exception):
    """Raised when SMTP message dispatch fails after bounded retries."""
    pass

PLAIN_TEXT_TEMPLATE = """Hello,

Your verification code for SafeStrata Context Engine is: {{ code }}

This code is single-use and will expire in {{ expire_minutes }} minutes.

If you did not request this verification code, please ignore this email. Never share this code with anyone.

— SafeStrata Context Engine Team
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>SafeStrata Verification Code</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f17; color: #f1f5f9; margin: 0; padding: 24px; }
    .container { max-width: 480px; margin: 0 auto; background-color: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
    .header { font-size: 20px; font-weight: 700; color: #38bdf8; margin-bottom: 8px; }
    .subtitle { font-size: 14px; color: #94a3b8; margin-bottom: 24px; }
    .code-box { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; text-align: center; padding: 20px; margin: 24px 0; font-family: 'JetBrains Mono', monospace, Courier; font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #10b981; }
    .notice { font-size: 13px; color: #94a3b8; line-height: 1.5; margin-bottom: 16px; }
    .footer { font-size: 12px; color: #64748b; border-top: 1px solid #1f2937; padding-top: 16px; margin-top: 24px; text-align: center; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">SafeStrata Context Engine</div>
    <div class="subtitle">Secure Passwordless Verification</div>
    <p style="margin: 0 0 16px; font-size: 14px; color: #cbd5e1;">Enter the following single-use verification code to complete sign in:</p>
    <div class="code-box">{{ code }}</div>
    <p class="notice">This code will expire in <strong>{{ expire_minutes }} minutes</strong>. If you did not request this email, no action is required.</p>
    <p class="notice" style="color: #ef4444;">Never share this code with anyone. SafeStrata staff will never ask for your verification code.</p>
    <div class="footer">SafeStrata Context Engine • Automated Security Notification</div>
  </div>
</body>
</html>
"""

class EmailService:
    def __init__(self):
        self.plain_template = Template(PLAIN_TEXT_TEMPLATE)
        self.html_template = Template(HTML_TEMPLATE)

    def create_message(self, to_email: str, code: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your SafeStrata Verification Code"
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email
        msg["Reply-To"] = settings.SMTP_FROM

        domain = settings.SMTP_FROM.split("@")[-1] if "@" in settings.SMTP_FROM else "safestrata.local"
        msg["Message-ID"] = make_msgid(domain=domain)
        msg["Date"] = formatdate(localtime=True)

        text_body = self.plain_template.render(code=code, expire_minutes=settings.OTP_EXPIRE_MINUTES)
        html_body = self.html_template.render(code=code, expire_minutes=settings.OTP_EXPIRE_MINUTES)

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        return msg

    async def send_otp_email(self, to_email: str, code: str, max_retries: int = 2) -> None:
        """Sends genuine OTP code via aiosmtplib with strict TLS enforcement and retry bounds."""
        # 1. Environment and configuration checks
        if settings.APP_ENV == "production":
            if not settings.SMTP_HOST:
                raise SMTPConfigurationError("SMTP_HOST must be configured in production environment.")
            if not (settings.SMTP_STARTTLS or settings.SMTP_SSL):
                raise SMTPConfigurationError("TLS or SSL is strictly required for SMTP authentication in production.")
        elif settings.APP_ENV == "development":
            if not settings.SMTP_HOST:
                logger.warning(
                    "SMTP not configured in development mode. Verification email dispatched to console mock handler."
                )
                return

        msg = self.create_message(to_email=to_email, code=code)

        # 2. Async SMTP delivery with bounded retry
        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                smtp = aiosmtplib.SMTP(
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    use_tls=settings.SMTP_SSL,
                    start_tls=(settings.SMTP_STARTTLS and not settings.SMTP_SSL),
                    timeout=settings.SMTP_TIMEOUT_SECONDS
                )
                await smtp.connect()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                await smtp.send_message(msg)
                await smtp.quit()
                logger.info(f"Verification email dispatched to {to_email}")
                return
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    await asyncio.sleep(0.5)

        logger.error(f"SMTP delivery failed for {to_email} after {max_retries} retries: {last_error}")
        raise SMTPDeliveryError(f"Email delivery service temporarily unavailable: {last_error}")

email_service = EmailService()
