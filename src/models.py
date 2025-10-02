from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON, ForeignKey
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    google_id = Column(String, unique=True, index=True)
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expiry = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    emails = relationship("Email", back_populates="user")

class Email(Base):
    __tablename__ = "emails"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    msg_id = Column(String, unique=True, index=True)
    thread_id = Column(String, index=True)
    from_addr = Column(String)
    to_addr = Column(String)
    subject = Column(String)
    snippet = Column(Text)
    received_at = Column(DateTime, default=datetime.utcnow)
    raw_path = Column(String)
    labels_json = Column(JSON, default=dict)
    is_read = Column(Boolean, default=False)  # Track read/unread status
    replied_at = Column(DateTime, nullable=True)  # Track when user replied to this email
    user = relationship("User", back_populates="emails")
    inferences = relationship("Inference", back_populates="email")
    drafts = relationship("Draft", back_populates="email")

class Inference(Base):
    __tablename__ = "inferences"
    id = Column(Integer, primary_key=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    kind = Column(String)  # classification|summary|reply_options
    json = Column(JSON)
    model = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    email = relationship("Email", back_populates="inferences")

class Draft(Base):
    __tablename__ = "drafts"
    id = Column(Integer, primary_key=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    draft_text = Column(Text)
    confidence = Column(Integer)
    style = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    email = relationship("Email", back_populates="drafts")

class ComposedDraft(Base):
    """User-composed email drafts (not AI-generated)"""
    __tablename__ = "composed_drafts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_addr = Column(Text, nullable=False)  # Can be multiple, comma-separated
    cc_addr = Column(Text, nullable=True)
    bcc_addr = Column(Text, nullable=True)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    reply_to_email_id = Column(Integer, ForeignKey("emails.id"), nullable=True)  # If this is a reply
    is_reply = Column(Boolean, default=False)
    is_forward = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)  # NULL if not sent yet
    reply_to_email = relationship("Email", foreign_keys=[reply_to_email_id])
