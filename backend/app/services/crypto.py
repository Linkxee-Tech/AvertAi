from cryptography.fernet import Fernet
from app.core.config import get_settings

settings = get_settings()

_fernet = Fernet(settings.ENCRYPTION_KEY.encode() if settings.ENCRYPTION_KEY else Fernet.generate_key())

def encrypt_string(plain_text: str) -> str:
    if not plain_text:
        return plain_text
    return _fernet.encrypt(plain_text.encode()).decode()

def decrypt_string(encrypted_text: str) -> str:
    if not encrypted_text:
        return encrypted_text
    try:
        return _fernet.decrypt(encrypted_text.encode()).decode()
    except Exception:
        # Fallback to plain text if decryption fails (e.g., during migration)
        return encrypted_text
