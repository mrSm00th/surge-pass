import asyncio

from src.app.core.celery_app import celery_app
from src.app.core.config import settings
from src.app.core.email import send_email
from src.app.core.email_render import render_email_template


@celery_app.task(name="users.send_otp_email")
def send_otp_email_task(
    otp: str,
    to_email: str,
):

    asyncio.run(send_otp_email(otp, to_email))


async def send_otp_email(
    otp: str,
    to_email: str,
):

    subject = "Email Verification with OTP"

    plain_text = f"""
    Email Verification

    Your One-Time Password (OTP) is: {otp}

    This code will expire in 10 minutes. Please do not share this code with anyone.

    If you did not request this verification, please ignore this email.

    ---
    This is an automated message, please do not reply.
    """

    html_content = render_email_template(
        "email_verification.html",
        otp=otp,
        expire_minutes=settings.otp_expire_minutes,
    )

    await send_email(
        to_email=to_email,
        subject=subject,
        plain_text=plain_text,
        html_content=html_content,
    )


@celery_app.task(name="users.send_password_reset_email")
def send_password_reset_email_task(
    to_email: str,
    name: str,
    reset_token: str,
):

    asyncio.run(send_password_reset_email(to_email, name, reset_token))


async def send_password_reset_email(
    to_email: str,
    name: str,
    reset_token: str,
) -> None:
    reset_url = (
        f"{settings.frontend_url}/reset-password?token={reset_token}&email={to_email}"
    )

    plain_text = f"""Hi {name},

We received a request to reset your surgepass password.

Click the link below to set a new password:
{reset_url}

This link expires in {settings.otp_expire_minutes} minutes.
If you did not request this, ignore this email.

- surgepass Team
"""

    html_content = render_email_template(
        "password_reset.html",
        name=name,
        reset_url=reset_url,
        expire_minutes=settings.otp_expire_minutes,
    )

    await send_email(
        to_email=to_email,
        subject="Reset your password - surgepass",
        plain_text=plain_text,
        html_content=html_content,
    )
