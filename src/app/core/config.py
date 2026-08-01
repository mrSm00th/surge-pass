from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    access_token_expire_minutes: int
    access_token_secret_key: SecretStr
    access_token_signing_algorithm: str

    refresh_token_expire_days: int = 30

    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    mail_from_name: str
    mail_from: str
    mail_use_tls: bool = True

    otp_expire_minutes: int

    frontend_url: str = "http://localhost:3000"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
