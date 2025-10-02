"""
Authentication and session management for AgentMail.
"""

import json
from datetime import datetime, timedelta
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from .config import settings
from .models import User

# Session serializer
serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

def create_session_token(user_id: int) -> str:
    """Create a secure session token for a user."""
    return serializer.dumps(user_id, salt='session')

def verify_session_token(token: str, max_age: int = 86400 * 7) -> Optional[int]:
    """Verify a session token and return the user ID."""
    try:
        user_id = serializer.loads(token, salt='session', max_age=max_age)
        return user_id
    except BadSignature:
        return None

def get_google_oauth_flow():
    """Create a Google OAuth flow."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise ValueError("Google OAuth credentials not configured")
    
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=settings.GOOGLE_SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
    
    return flow

def get_authorization_url() -> tuple[str, str]:
    """Get the Google OAuth authorization URL and state."""
    flow = get_google_oauth_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return authorization_url, state

def exchange_code_for_tokens(code: str, state: str) -> dict:
    """Exchange authorization code for tokens."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting token exchange...")
        flow = get_google_oauth_flow()
        # Disable scope checking - Google adds 'openid' automatically which causes validation to fail
        import os
        os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
        flow.fetch_token(code=code)
        
        credentials = flow.credentials
        logger.info("Token exchange successful, getting user info...")
        
        # Get user info
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        logger.info(f"User info retrieved: {user_info.get('email')}")
        
        return {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_expiry': credentials.expiry,
            'email': user_info.get('email'),
            'name': user_info.get('name'),
            'google_id': user_info.get('id'),
            'picture': user_info.get('picture')
        }
    except Exception as e:
        logger.error(f"Token exchange failed: {str(e)}")
        raise

def create_or_update_user(db: Session, user_data: dict) -> User:
    """Create or update a user from OAuth data."""
    user = db.query(User).filter(User.google_id == user_data['google_id']).first()
    
    if user:
        # Update existing user
        user.access_token = user_data['access_token']
        if user_data.get('refresh_token'):
            user.refresh_token = user_data['refresh_token']
        user.token_expiry = user_data['token_expiry']
        user.last_login = datetime.utcnow()
        user.name = user_data['name']
    else:
        # Create new user
        user = User(
            email=user_data['email'],
            name=user_data['name'],
            google_id=user_data['google_id'],
            access_token=user_data['access_token'],
            refresh_token=user_data.get('refresh_token'),
            token_expiry=user_data['token_expiry']
        )
        db.add(user)
    
    db.commit()
    db.refresh(user)
    return user

def get_user_credentials(user: User) -> Credentials:
    """Get Google API credentials for a user."""
    credentials = Credentials(
        token=user.access_token,
        refresh_token=user.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET
    )
    
    # Check if token needs refresh
    if user.token_expiry and user.token_expiry < datetime.utcnow():
        # TODO: Implement token refresh
        pass
    
    return credentials

def get_current_user(db: Session, session_token: Optional[str]) -> Optional[User]:
    """Get the current user from session token."""
    if not session_token:
        return None
    
    user_id = verify_session_token(session_token)
    if not user_id:
        return None
    
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user
