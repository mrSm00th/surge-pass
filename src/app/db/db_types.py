from typing import Any

from sqlalchemy import Text, TypeDecorator

from src.app.core.encrption import decrypt_data, encrypt_data


class EncryptedString(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(
        self,
        value: str | None,
        dialect: Any,
    ) -> str | None:

        if value is None:
            return None

        # encrypt_data returns a decoded str, which safe to store in Text column
        return encrypt_data(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:

        if value is None:
            return None
        return decrypt_data(value)
