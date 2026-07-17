import os
import base64
import hashlib
import secrets
from cryptography.fernet import Fernet

def _derive_key(password: str, salt: bytes) -> bytes:
    """
    Derive a 32‑byte key from password and salt using PBKDF2-HMAC-SHA256.
    Returns raw key bytes suitable for Fernet (url‑safe base64 encoded).
    """
    # PBKDF2 with 100_000 iterations
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    # Fernet expects url-safe base64-encoded 32‑byte key
    return base64.urlsafe_b64encode(dk)

def encrypt_data(plaintext: str, password: str, salt: bytes) -> str:
    """Encrypt a string using a key derived from password+salt.
    Returns base64‑encoded ciphertext."""
    if not plaintext:
        return ''
    key = _derive_key(password, salt)
    f = Fernet(key)
    encrypted = f.encrypt(plaintext.encode('utf-8'))
    return base64.urlsafe_b64encode(encrypted).decode('utf-8')

def decrypt_data(ciphertext_b64: str, password: str, salt: bytes) -> str:
    """Decrypt a ciphertext produced by encrypt_data."""
    if not ciphertext_b64:
        return ''
    key = _derive_key(password, salt)
    f = Fernet(key)
    decoded = base64.urlsafe_b64decode(ciphertext_b64.encode('utf-8'))
    decrypted = f.decrypt(decoded)
    return decrypted.decode('utf-8')

def hash_password(password: str, salt: bytes) -> str:
    """Return a hex string of PBKDF2‑SHA256 hash of password+salts."""
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return dk.hex()

def verify_password(password: str, salt: bytes, stored_hash: str) -> bool:
    """Check if password matches the stored hash."""
    return hash_password(password, salt) == stored_hash

def generate_salt() -> bytes:
    """Generate a random 16‑byte salt."""
    return secrets.token_bytes(16)
