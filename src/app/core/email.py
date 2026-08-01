import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from src.app.core.config import settings
import ssl
import certifi


async def send_email(
    to_email: str,
    subject: str,
    plain_text: str,
    html_content: str | None = None,
):

    message = MIMEMultipart("alternative")
    message["From"] = f"{settings.mail_from_name} <{settings.mail_from}>"
    message["To"] = to_email
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message["Reply-To"] = settings.mail_from

    message.attach(MIMEText(plain_text, "plain"))

    if html_content:
        message.attach(MIMEText(html_content, "html"))

    tls_context = ssl.create_default_context(cafile=certifi.where())

    smtp_kwargs = {
        "hostname": settings.smtp_host,
        "port": settings.smtp_port,
        "username": settings.smtp_user,
        "password": settings.smtp_password,
        "tls_context": tls_context,
        "timeout": 15,
    }

    if settings.mail_use_tls:
        smtp_kwargs["start_tls"] = True
    else:
        smtp_kwargs["use_tls"] = True

    try:
        await aiosmtplib.send(message, **smtp_kwargs)

    except aiosmtplib.SMTPAuthenticationError:
        # TODO log in logger
        raise

    except aiosmtplib.SMTPConnectTimeoutError:
        raise

    except aiosmtplib.SMTPException:
        raise

    except Exception:
        raise


async def send_otp_email(
    otp: str,
    to_email: str,
    subject: str | None = None,
    plain_text: str | None = None,
    html_content: str | None = None,
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

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Verification</title>
    </head>
    <body style="margin:0; padding:0; background-color:#f4f4f7; font-family: Arial, Helvetica, sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7; padding:40px 0;">
        <tr>
        <td align="center">
            <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
            <tr>
                <td style="padding:32px 32px 16px 32px; text-align:center;">
                <h2 style="margin:0; color:#1a1a1a; font-size:20px;">Verify Your Email</h2>
                </td>
            </tr>
            <tr>
                <td style="padding:0 32px 24px 32px; text-align:center;">
                <p style="margin:0; color:#555555; font-size:14px; line-height:1.5;">
                    Use the code below to verify your email address. This code is valid for 10 minutes.
                </p>
                </td>
            </tr>
            <tr>
                <td style="padding:0 32px 32px 32px; text-align:center;">
                <div style="display:inline-block; background-color:#f0f0f5; border-radius:6px; padding:16px 32px;">
                    <span style="font-size:32px; font-weight:bold; letter-spacing:8px; color:#1a1a1a;">{otp}</span>
                </div>
                </td>
            </tr>
            <tr>
                <td style="padding:0 32px 32px 32px; text-align:center;">
                <p style="margin:0; color:#999999; font-size:12px; line-height:1.5;">
                    If you did not request this code, you can safely ignore this email.
                </p>
                </td>
            </tr>
            <tr>
                <td style="background-color:#f9f9fb; padding:16px 32px; text-align:center;">
                <p style="margin:0; color:#aaaaaa; font-size:11px;">
                    This is an automated message, please do not reply.
                </p>
                </td>
            </tr>
            </table>
        </td>
        </tr>
    </table>
    </body>
    </html>
    """

    await send_email(
        to_email=to_email,
        subject=subject,
        plain_text=plain_text,
        html_content=html_content,
    )


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

    html_content = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #333;">
    <p>Hi {name},</p>
    <p>We received a request to reset your password.</p>
    <p><a href="{reset_url}">Reset your password</a></p>
    <p>This link expires in {settings.otp_expire_minutes} minutes. If you did not request this, ignore this email.</p>
    <p>— Feasto Team</p>
</body>
</html>
"""

    await send_email(
        to_email=to_email,
        subject="Reset your password - surgepass",
        plain_text=plain_text,
        html_content=html_content,
    )
