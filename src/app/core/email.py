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
        raise
    except aiosmtplib.SMTPConnectTimeoutError:
        raise
    except aiosmtplib.SMTPException:
        raise
    except Exception:
        raise
