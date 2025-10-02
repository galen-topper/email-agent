"""
Gmail API client using OAuth credentials for authenticated users.
"""

import logging
import base64
import email
from typing import List, Dict, Any, Callable, Set
from googleapiclient.discovery import build
from .models import User
from . import auth

logger = logging.getLogger(__name__)

def fetch_user_emails(user: User, save_callback: Callable[[Dict[str, Any]], None], max_results: int = 10) -> List[Dict[str, Any]]:
    """Fetch emails for a user using Gmail API with their OAuth credentials."""
    emails = []
    
    try:
        # Get user's credentials
        credentials = auth.get_user_credentials(user)
        
        # Build Gmail API service
        service = build('gmail', 'v1', credentials=credentials)
        
        # Get list of messages (fetch all emails, not just unread)
        results = service.users().messages().list(
            userId='me',
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        logger.info(f"Found {len(messages)} emails for user {user.email}")
        
        if not messages:
            return emails
        
        # Fetch full message details for each
        for msg in messages:
            try:
                message = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()
                
                # Parse message data
                email_data = parse_gmail_message(message, user.id)
                
                if email_data:
                    save_callback(email_data)
                    emails.append(email_data)
                    logger.info(f"Processed email: {email_data['subject'][:50]}...")
                    
            except Exception as e:
                logger.error(f"Error processing message {msg['id']}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Gmail API fetch failed: {e}")
        raise
    
    return emails

def parse_gmail_message(message: dict, user_id: int) -> Dict[str, Any]:
    """Parse a Gmail API message into our email format."""
    headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
    
    # Extract body
    body = get_message_body(message['payload'])
    
    # Parse timestamp from internalDate (milliseconds since epoch)
    received_at = None
    if 'internalDate' in message:
        try:
            # Gmail internalDate is in milliseconds, convert to seconds for datetime
            timestamp_ms = int(message['internalDate'])
            from datetime import datetime
            received_at = datetime.fromtimestamp(timestamp_ms / 1000.0)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse timestamp: {e}")
            # Fallback to parsing Date header
            date_str = headers.get('Date', '')
            if date_str:
                received_at = parse_date_header(date_str)
    
    # Determine if email is read based on Gmail labels
    # In Gmail, if 'UNREAD' label is present, email is unread
    # If 'UNREAD' label is NOT present, email is read
    labels = message.get('labelIds', [])
    is_read = 'UNREAD' not in labels
    
    return {
        'msg_id': message['id'],
        'thread_id': message['threadId'],
        'from_addr': headers.get('From', ''),
        'to_addr': headers.get('To', ''),
        'subject': headers.get('Subject', ''),
        'snippet': message.get('snippet', '')[:500],
        'raw_path': f"gmail_api_{message['id']}",  # Not storing raw for API messages
        'received_at': received_at,
        'labels_json': {'labels': labels},
        'is_read': is_read,  # Sync read status from Gmail
        'user_id': user_id
    }

def parse_date_header(date_str: str):
    """Parse email Date header into datetime object."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str)
    except Exception as e:
        logger.warning(f"Failed to parse date header '{date_str}': {e}")
        return None

def get_message_body(payload: dict) -> str:
    """Extract body text from Gmail message payload."""
    if 'body' in payload and 'data' in payload['body']:
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                if 'data' in part['body']:
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
            elif 'parts' in part:
                # Recursive for nested parts
                body = get_message_body(part)
                if body:
                    return body
    
    return ""


def fetch_user_contacts(user: User, query: str = None, max_results: int = 50) -> List[Dict[str, str]]:
    """
    Fetch contacts from Gmail People API and past email interactions.
    Returns a list of contacts with name and email, sorted by frequency when no query.
    """
    contacts = []
    seen_emails: Set[str] = set()
    email_frequency = {}  # Track how often each email appears
    
    try:
        # Get user's credentials
        credentials = auth.get_user_credentials(user)
        
        # Build Gmail and People API services
        people_service = build('people', 'v1', credentials=credentials)
        gmail_service = build('gmail', 'v1', credentials=credentials)
        
        # 1. Fetch from People API (Google Contacts)
        try:
            results = people_service.people().connections().list(
                resourceName='people/me',
                pageSize=100,
                personFields='names,emailAddresses'
            ).execute()
            
            connections = results.get('connections', [])
            logger.info(f"Found {len(connections)} contacts from People API for user {user.email}")
            
            for person in connections:
                names = person.get('names', [])
                emails = person.get('emailAddresses', [])
                
                if names and emails:
                    name = names[0].get('displayName', '')
                    for email_obj in emails:
                        email_addr = email_obj.get('value', '').lower()
                        if email_addr and email_addr not in seen_emails:
                            contacts.append({
                                'name': name,
                                'email': email_addr
                            })
                            seen_emails.add(email_addr)
                            email_frequency[email_addr] = email_frequency.get(email_addr, 0) + 1
        except Exception as e:
            logger.warning(f"Could not fetch from People API: {e}")
        
        # 2. Fetch from recent email interactions (To, From, Cc fields)
        # Track frequency to show most-contacted people first
        try:
            # Get recent messages
            results = gmail_service.users().messages().list(
                userId='me',
                maxResults=200  # Check more emails for contact extraction
            ).execute()
            
            messages = results.get('messages', [])
            
            for msg in messages[:100]:  # Process first 100 for contacts
                try:
                    message = gmail_service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='metadata',
                        metadataHeaders=['From', 'To', 'Cc']
                    ).execute()
                    
                    headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
                    
                    # Extract contacts from From, To, Cc
                    for header in ['From', 'To', 'Cc']:
                        if header in headers:
                            extracted = extract_email_addresses(headers[header])
                            for name, email_addr in extracted:
                                email_lower = email_addr.lower()
                                
                                # Count frequency
                                email_frequency[email_lower] = email_frequency.get(email_lower, 0) + 1
                                
                                if email_lower not in seen_emails:
                                    contacts.append({
                                        'name': name or email_addr,
                                        'email': email_lower
                                    })
                                    seen_emails.add(email_lower)
                except Exception as e:
                    continue
                    
        except Exception as e:
            logger.warning(f"Could not fetch contacts from email history: {e}")
        
        # Filter by query if provided
        if query:
            query_lower = query.lower()
            contacts = [
                c for c in contacts 
                if query_lower in c['name'].lower() or query_lower in c['email'].lower()
            ]
            # Sort filtered results alphabetically
            contacts.sort(key=lambda x: x['name'].lower())
        else:
            # No query: sort by frequency (most contacted first), then by name
            contacts.sort(key=lambda x: (-email_frequency.get(x['email'], 0), x['name'].lower()))
        
        # Limit results
        contacts = contacts[:max_results]
        
        logger.info(f"Returning {len(contacts)} contacts for user {user.email}")
        return contacts
        
    except Exception as e:
        logger.error(f"Failed to fetch contacts: {e}")
        return []


def extract_email_addresses(header_value: str) -> List[tuple]:
    """
    Extract email addresses and names from email header.
    Returns list of (name, email) tuples.
    """
    import re
    from email.utils import getaddresses
    
    try:
        # Use email.utils.getaddresses to properly parse
        addresses = getaddresses([header_value])
        result = []
        
        for name, email_addr in addresses:
            if email_addr:
                # Clean up name
                name = name.strip().strip('"').strip("'")
                email_addr = email_addr.strip().lower()
                
                # Skip invalid emails
                if '@' in email_addr and '.' in email_addr:
                    result.append((name, email_addr))
        
        return result
    except Exception as e:
        logger.warning(f"Failed to parse email addresses from '{header_value}': {e}")
        return []


def mark_email_as_read_in_gmail(user: User, msg_id: str, is_read: bool = True):
    """Mark an email as read or unread in Gmail."""
    try:
        from googleapiclient.discovery import build
        
        # Get user's credentials
        credentials = auth.get_user_credentials(user)
        
        # Build Gmail API service
        service = build('gmail', 'v1', credentials=credentials)
        
        if is_read:
            # Remove UNREAD label to mark as read
            service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked email {msg_id} as read in Gmail")
        else:
            # Add UNREAD label to mark as unread
            service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={'addLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked email {msg_id} as unread in Gmail")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to update read status in Gmail for {msg_id}: {e}")
        return False
