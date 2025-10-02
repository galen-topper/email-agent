import smtplib
import logging
import base64
from email.message import EmailMessage
from email.utils import formataddr
from .config import settings
from .models import User
from . import auth

logger = logging.getLogger(__name__)

def send_email_smtp(to_addr: str, subject: str, body: str, cc_addr: str = None, bcc_addr: str = None, user: User = None) -> bool:
    """Send an email via Gmail API using OAuth credentials."""
    try:
        from googleapiclient.discovery import build
        
        if not user:
            logger.error("No user provided for Gmail API send")
            return False
        
        # Get user's credentials
        credentials = auth.get_user_credentials(user)
        
        # Build Gmail API service
        service = build('gmail', 'v1', credentials=credentials)
        
        # Create email message
        msg = EmailMessage()
        msg["From"] = user.email
        msg["To"] = to_addr
        
        if cc_addr:
            msg["Cc"] = cc_addr
        if bcc_addr:
            msg["Bcc"] = bcc_addr
            
        msg["Subject"] = subject
        msg.set_content(body)
        
        # Encode message for Gmail API
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        message_body = {'raw': raw_message}
        
        # Send via Gmail API
        service.users().messages().send(userId='me', body=message_body).execute()
        
        logger.info(f"Email sent successfully to {to_addr}: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_addr}: {e}")
        return False

def send_email(to_addr: str, subject: str, body: str, reply_to_msg_id: str = None) -> bool:
    """Send an email via SMTP (legacy - prefer send_email_smtp with user)."""
    try:
        # Create email message
        msg = EmailMessage()
        
        # Set headers
        if settings.FROM_DISPLAY:
            msg["From"] = formataddr((settings.FROM_DISPLAY, settings.SMTP_USER))
        else:
            msg["From"] = settings.SMTP_USER
            
        msg["To"] = to_addr
        msg["Subject"] = subject
        
        # Add reply headers if this is a reply
        if reply_to_msg_id:
            msg["In-Reply-To"] = reply_to_msg_id
            msg["References"] = reply_to_msg_id
        
        # Set body content
        msg.set_content(body)
        
        # Send via SMTP
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {to_addr}: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_addr}: {e}")
        return False

def send_reply(original_email, draft_text: str) -> bool:
    """Send a reply to an original email."""
    # Add signature if not already present
    if settings.DEFAULT_SIGNATURE and not draft_text.endswith(settings.DEFAULT_SIGNATURE):
        draft_text += settings.DEFAULT_SIGNATURE
    
    # Determine reply subject
    subject = original_email.subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    
    return send_email(
        to_addr=original_email.from_addr,
        subject=subject,
        body=draft_text,
        reply_to_msg_id=original_email.msg_id
    )
