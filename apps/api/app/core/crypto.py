from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import Text, TypeDecorator

from app.core.config import get_settings

CUSTOMER_DATA_PREFIX = "cpf:v1:"


def validate_fernet_key(key: str | bytes | None, setting_name: str) -> None:
    if not key:
        raise RuntimeError(f"{setting_name} is required.")
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:  # pragma: no cover - exact cryptography exception is not contract surface
        raise RuntimeError(f"{setting_name} must be a valid Fernet key.") from exc


def validate_customer_data_encryption_key(key: str | bytes | None) -> None:
    validate_fernet_key(key, "CUSTOMER_DATA_ENCRYPTION_KEY")


def validate_plaid_token_encryption_key(key: str | bytes | None) -> None:
    validate_fernet_key(key, "PLAID_TOKEN_ENCRYPTION_KEY")


@lru_cache(maxsize=8)
def _fernet_for_key(key: str | bytes) -> Fernet:
    return Fernet(key.encode() if isinstance(key, str) else key)


def _customer_data_key() -> str | None:
    return get_settings().customer_data_encryption_key


def encrypt_customer_value(value):
    if value is None:
        return None
    text = str(value)
    if not text or text.startswith(CUSTOMER_DATA_PREFIX):
        return text
    key = _customer_data_key()
    if not key:
        return text
    token = _fernet_for_key(key).encrypt(text.encode("utf-8")).decode("ascii")
    return f"{CUSTOMER_DATA_PREFIX}{token}"


def decrypt_customer_value(value):
    if value is None:
        return None
    text = str(value)
    if not text.startswith(CUSTOMER_DATA_PREFIX):
        return text
    key = _customer_data_key()
    if not key:
        raise RuntimeError("CUSTOMER_DATA_ENCRYPTION_KEY is required to decrypt stored customer data.")
    token = text[len(CUSTOMER_DATA_PREFIX) :]
    try:
        return _fernet_for_key(key).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored customer data could not be decrypted with the configured key.") from exc


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, *args, redact_card_data: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.redact_card_data = redact_card_data

    def process_bind_param(self, value, dialect):
        return encrypt_customer_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_customer_value(value)
