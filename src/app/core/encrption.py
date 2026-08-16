from cryptography.fernet import Fernet

from src.app.core.config import settings

fernet = Fernet(settings.fernet_key)


def encrypt_data(data: str) -> str:
    return fernet.encrypt(data.encode("utf-8")).decode("utf-8")


def decrypt_data(data: str) -> str:
    return fernet.decrypt(data.encode("utf-8")).decode("utf-8")
