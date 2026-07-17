from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from .security import encrypt_data, decrypt_data, generate_salt
import os

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(32), nullable=False)  # hex encoded salt
    # Encrypted IMAP settings
    encrypted_imap_server = Column(String(500), nullable=True)
    encrypted_imap_port = Column(String(500), nullable=True)  # store as encrypted string
    encrypted_imap_folder = Column(String(500), nullable=True)
    # relationships
    emails = relationship("EmailItem", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", cascade="all, delete-orphan")
    def __repr__(self):
        return f"<User {self.email}>"

    def set_password(self, password: str):
        """Hash password with PBKDF2 using werkzeug's generate_password_hash."""
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)
        # generate a random salt for encryption (different from password hash salt)
        self.salt = generate_salt().hex()

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def set_imap_config(self, server: str, port: int, folder: str, password: str):
        """Encrypt and store IMAP configuration using the user's password as key."""
        # Use the user's password (not hash) to derive encryption key
        enc_server = encrypt_data(server, password, bytes.fromhex(self.salt))
        enc_port = encrypt_data(str(port), password, bytes.fromhex(self.salt))
        enc_folder = encrypt_data(folder, password, bytes.fromhex(self.salt))
        self.encrypted_imap_server = enc_server
        self.encrypted_imap_port = enc_port
        self.encrypted_imap_folder = enc_folder

    def get_imap_config(self, password: str):
        """Return (server, port, folder) decrypted using user's password."""
        if not (self.encrypted_imap_server and self.encrypted_imap_port and self.encrypted_imap_folder):
            return None, None, None
        server = decrypt_data(self.encrypted_imap_server, password, bytes.fromhex(self.salt))
        port = decrypt_data(self.encrypted_imap_port, password, bytes.fromhex(self.salt))
        folder = decrypt_data(self.encrypted_imap_folder, password, bytes.fromhex(self.salt))
        try:
            port_int = int(port)
        except:
            port_int = 993
        return server, port_int, folder

class EmailItem(Base):
    __tablename__ = 'emails'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_id = Column(String(255), unique=True, nullable=False)
    sender = Column(String(255), nullable=True)
    subject = Column(String(255), nullable=True)
    date = Column(DateTime, nullable=True)
    snippet = Column(Text, nullable=True)
    label = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="emails")
    def __repr__(self):
        return f"<Email {self.message_id}>"

class UserPreference(Base):
    __tablename__ = 'user_preferences'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=True)  # store JSON or plain text
    __table_args__ = (UniqueConstraint('user_id', 'key', name='_user_key_uc'),)
    user = relationship("User", back_populates="preferences")
    def __repr__(self):
        return f"<UserPreference {self.key}: {self.value}>"
