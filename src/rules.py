"""
Simple heuristic rules for email classification before LLM processing.
These provide cheap wins and can help reduce LLM costs.
"""

import re
from typing import Dict, Any

# Priority domains that should be marked as high priority
HIGH_PRIORITY_DOMAINS = {
    "@stanford.edu",
    "@judgmentlabs.ai",
    # Add your important domains here
}

# Keywords that indicate high priority
HIGH_PRIORITY_KEYWORDS = {
    "interview", "offer", "invoice", "overdue", "refund", 
    "escalation", "legal", "deadline", "urgent", "asap",
    "deadline", "due date", "contract", "agreement"
}

# Spam indicators
SPAM_KEYWORDS = {
    "unsubscribe", "click here", "limited time", "act now",
    "congratulations", "you've won", "free money", "viagra",
    "casino", "lottery", "inheritance"
}

# Domains that are likely spam
SPAM_DOMAINS = {
    # Add known spam domains here
}

def apply_heuristic_rules(subject: str, body: str, from_addr: str) -> Dict[str, Any]:
    """
    Apply heuristic rules to classify an email before LLM processing.
    Returns a dict with suggested overrides or None if no rules apply.
    """
    subject_lower = subject.lower()
    body_lower = body.lower()
    from_addr_lower = from_addr.lower()
    
    # Check for high priority domains
    for domain in HIGH_PRIORITY_DOMAINS:
        if domain in from_addr_lower:
            return {
                "priority": "high",
                "is_spam": False,
                "action": "needs_reply",
                "reasons": [f"High priority domain: {domain}"]
            }
    
    # Check for high priority keywords
    for keyword in HIGH_PRIORITY_KEYWORDS:
        if keyword in subject_lower or keyword in body_lower:
            return {
                "priority": "high",
                "is_spam": False,
                "action": "needs_reply",
                "reasons": [f"High priority keyword: {keyword}"]
            }
    
    # Check for spam indicators
    for keyword in SPAM_KEYWORDS:
        if keyword in subject_lower or keyword in body_lower:
            return {
                "priority": "low",
                "is_spam": True,
                "action": "archive",
                "reasons": [f"Spam keyword: {keyword}"]
            }
    
    # Check for spam domains
    for domain in SPAM_DOMAINS:
        if domain in from_addr_lower:
            return {
                "priority": "low",
                "is_spam": True,
                "action": "archive",
                "reasons": [f"Spam domain: {domain}"]
            }
    
    # Check for thread length and questions (needs_reply heuristic)
    if "?" in subject or "?" in body:
        # Count email addresses in body to estimate thread length
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_count = len(re.findall(email_pattern, body))
        
        if email_count > 4:  # Likely a long thread
            return {
                "priority": "normal",
                "is_spam": False,
                "action": "needs_reply",
                "reasons": ["Long thread with question"]
            }
    
    return None  # No rules apply, use LLM classification
