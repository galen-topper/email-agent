import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # IMAP Configuration (legacy, for backward compatibility)
    IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
    IMAP_USER = os.getenv("IMAP_USER")
    IMAP_PASS = os.getenv("IMAP_PASS")
    
    # SMTP Configuration (legacy, for backward compatibility)
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASS = os.getenv("SMTP_PASS")
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
    
    # Session Configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "agentmail_session")
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    MODEL_NAME = os.getenv("MODEL_NAME", "gpt-5")  # Using GPT-5
    
    # Application Settings
    DB_URL = os.getenv("DB_URL", "sqlite:///./email_agent.db")
    POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", 120))
    FROM_DISPLAY = os.getenv("FROM_DISPLAY", "")
    DEFAULT_SIGNATURE = os.getenv("DEFAULT_SIGNATURE", "")
    
    # OAuth Scopes
    GOOGLE_SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'https://www.googleapis.com/auth/contacts.readonly'  # For People API (contacts)
    ]

settings = Settings()

