import os
import uuid
import pathlib
import logging
import email
import re
import ssl
from typing import List, Dict, Any, Callable
from imapclient import IMAPClient
from .config import settings

logger = logging.getLogger(__name__)

# Create raw directory for storing email files
RAW_DIR = pathlib.Path("./raw")
RAW_DIR.mkdir(exist_ok=True)

def fetch_unseen_emails(save_callback: Callable[[Dict[str, Any]], None]) -> List[Dict[str, Any]]:
    """Fetch unseen emails from IMAP server and call save_callback for each."""
    emails = []
    
    try:
        # Create SSL context that handles certificate verification properly
        ssl_context = ssl.create_default_context()
        
        with IMAPClient(settings.IMAP_HOST, ssl_context=ssl_context) as server:
            server.login(settings.IMAP_USER, settings.IMAP_PASS)
            server.select_folder("INBOX")
            
            # Search for unseen emails
            uids = server.search(["UNSEEN"])
            logger.info(f"Found {len(uids)} unseen emails")
            
            if not uids:
                return emails
            
            # Fetch email data
            for uid, msg_data in server.fetch(uids, [b"RFC822"]).items():
                try:
                    raw_bytes = msg_data[b"RFC822"]
                    
                    # Parse email using Python's built-in email module
                    parsed = email.message_from_bytes(raw_bytes)
                    
                    # Save raw email to file
                    raw_path = RAW_DIR / f"{uuid.uuid4()}.eml"
                    raw_path.write_bytes(raw_bytes)
                    
                    # Extract email data
                    email_data = {
                        "msg_id": parsed.get("Message-ID", f"uid_{uid}"),
                        "thread_id": _extract_thread_id(parsed),
                        "from_addr": _extract_from_addr(parsed),
                        "to_addr": _extract_to_addr(parsed),
                        "subject": parsed.get("Subject", ""),
                        "snippet": _extract_snippet(parsed),
                        "raw_path": str(raw_path),
                        "received_at": _parse_date(parsed.get("Date")),
                        "labels_json": {}
                    }
                    
                    # Call save callback
                    save_callback(email_data)
                    emails.append(email_data)
                    
                    logger.info(f"Processed email: {email_data['subject'][:50]}...")
                    
                except Exception as e:
                    logger.error(f"Error processing email UID {uid}: {e}")
                    continue
                    
    except Exception as e:
        logger.error(f"IMAP fetch failed: {e}")
        raise
    
    return emails

def _extract_thread_id(parsed) -> str:
    """Extract thread ID from email headers."""
    # Try References header first, then In-Reply-To, then Message-ID
    references = parsed.get("References", "")
    if references:
        # Take the last message ID from References
        ref_ids = references.split()
        if ref_ids:
            return ref_ids[-1]
    
    in_reply_to = parsed.get("In-Reply-To", "")
    if in_reply_to:
        return in_reply_to
    
    return parsed.get("Message-ID", "")

def _extract_from_addr(parsed) -> str:
    """Extract sender address."""
    from_header = parsed.get("From", "")
    if from_header:
        # Parse email address from "Name <email@domain.com>" format
        match = re.search(r'<([^>]+)>', from_header)
        if match:
            return match.group(1)
        # If no angle brackets, try to extract email-like string
        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', from_header)
        if email_match:
            return email_match.group(1)
    return ""

def _extract_to_addr(parsed) -> str:
    """Extract recipient addresses."""
    to_header = parsed.get("To", "")
    if to_header:
        # Extract all email addresses from the To header
        emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', to_header)
        return ",".join(emails)
    return ""

def _extract_snippet(parsed) -> str:
    """Extract a clean text snippet from the email."""
    # Try to get plain text content
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        text = payload.decode('utf-8', errors='ignore')
                        # Clean up the text
                        text = text.replace('\r\n', '\n').replace('\r', '\n')
                        # Take first 500 characters
                        return text[:500].strip()
                    except:
                        continue
    else:
        # Single part message
        if parsed.get_content_type() == "text/plain":
            payload = parsed.get_payload(decode=True)
            if payload:
                try:
                    text = payload.decode('utf-8', errors='ignore')
                    text = text.replace('\r\n', '\n').replace('\r', '\n')
                    return text[:500].strip()
                except:
                    pass
    
    # Fall back to HTML if no plain text
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        html = payload.decode('utf-8', errors='ignore')
                        # Simple HTML tag removal for snippet
                        clean_text = re.sub(r'<[^>]+>', '', html)
                        clean_text = clean_text.replace('\n', ' ').replace('\r', ' ')
                        # Clean up multiple spaces
                        clean_text = re.sub(r'\s+', ' ', clean_text)
                        return clean_text[:500].strip()
                    except:
                        continue
    else:
        if parsed.get_content_type() == "text/html":
            payload = parsed.get_payload(decode=True)
            if payload:
                try:
                    html = payload.decode('utf-8', errors='ignore')
                    clean_text = re.sub(r'<[^>]+>', '', html)
                    clean_text = clean_text.replace('\n', ' ').replace('\r', ' ')
                    clean_text = re.sub(r'\s+', ' ', clean_text)
                    return clean_text[:500].strip()
                except:
                    pass
    
    return ""

def _parse_date(date_str: str):
    """Parse email date string to datetime object."""
    if not date_str:
        return None
    
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except:
        return None

def mark_as_read(msg_id: str) -> bool:
    """Mark an email as read by its message ID."""
    try:
        with IMAPClient(settings.IMAP_HOST) as server:
            server.login(settings.IMAP_USER, settings.IMAP_PASS)
            server.select_folder("INBOX")
            
            # Search for the specific message ID
            uids = server.search([b"HEADER", b"Message-ID", msg_id.encode()])
            
            if uids:
                # Remove UNSEEN flag
                server.remove_flags(uids, [b"\\Seen"])
                logger.info(f"Marked email {msg_id} as read")
                return True
            else:
                logger.warning(f"Could not find email with Message-ID: {msg_id}")
                return False
                
    except Exception as e:
        logger.error(f"Failed to mark email as read: {e}")
        return False
