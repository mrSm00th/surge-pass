from cryptography.fernet import Fernet

from src.app.core.config import settings

fernet = Fernet(settings.fernet_key)


def encrypt_data(data: str) -> bytes:

    return fernet.encrypt(data.encode("utf-8"))


def decrypt_data(data: bytes) -> str:

    return fernet.decrypt(data).decode()
