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

# Scheduling / appointments / meetings
SCHEDULING_KEYWORDS = {
    "meeting", "meet", "calendar", "invite", "invitation", "rsvp",
    "appointment", "schedule", "scheduled", "reschedule", "availability",
    "zoom", "google meet", "meet.google.com", "calendar event", "ics",
    "begin:vcalendar", "outlook", "teams meeting"
}

# Time-sensitive phrases
TIME_SENSITIVE_PATTERNS = [
    r"\bby\s+eod\b",
    r"\btoday\b",
    r"\btomorrow\b",
    r"\bwithin\s+\d+\s*(hours|hrs|days)\b",
    r"\bin\s+\d+\s*(hours|hrs|days)\b",
    r"\bdeadline\b",
    r"\bdue\b",
    r"\burgent\b",
    r"\basap\b",
    r"\btime[- ]sensitive\b"
]

# Spam indicators
SPAM_KEYWORDS = {
    "unsubscribe", "click here", "limited time", "act now",
    "congratulations", "you've won", "free money", "viagra",
    "casino", "lottery", "inheritance", "shop now", "buy now",
    "special offer", "exclusive deal", "save now", "don't miss",
    "flash sale", "clearance", "today only", "hurry", "expires soon",
    "% off", "percent off", "discount", "promo code", "coupon",
    "black friday", "cyber monday", "holiday sale", "free shipping",
    "browse collection", "new arrivals", "just launched", "now available",
    "see what's new", "shop the", "explore our", "check out our",
    "limited stock", "while supplies last", "ending soon", "last chance"
}

# Promotional sender patterns (case insensitive)
PROMO_SENDER_PATTERNS = [
    "no-reply@", "noreply@", "donotreply@", "do-not-reply@",
    "marketing@", "promo@", "promotions@", "deals@", "offers@",
    "newsletter@", "news@", "updates@", "notifications@",
    "automated@", "auto@", "bounce@", "mailer@"
]

# Known retail/marketing domains
RETAIL_MARKETING_DOMAINS = {
    # E-commerce
    "amazon.com", "amazonselling", "amazonbusiness", "primevideo",
    "walmart.com", "target.com", "ebay.com", "etsy.com",
    "bestbuy.com", "homedepot.com", "lowes.com", "costco.com",
    "wayfair.com", "overstock.com", "zappos.com", "chewy.com",
    
    # Fashion/Apparel
    "gap.com", "oldnavy.com", "bananarepublic.com", "jcrew.com",
    "nordstrom.com", "macys.com", "kohls.com", "tjmaxx.com",
    "zara.com", "hm.com", "uniqlo.com", "nike.com", "adidas.com",
    
    # Subscriptions/Services
    "groupon.com", "livingsocial.com", "retailmenot.com",
    "slickdeals.net", "dealnews.com", "woot.com",
    
    # Marketing platforms
    "mailchimp.com", "sendgrid.net", "constantcontact.com",
    "customeriomail.com", "sendpulse.com", "hubspot.com",
    "salesforce.com", "marketo.com", "eloqua.com", "exacttarget.com",
    "em.com", "eml.cc", ".marketing", ".promo", ".deals"
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
    
    # Check for promotional sender patterns (no-reply@, marketing@, etc.)
    for pattern in PROMO_SENDER_PATTERNS:
        if pattern in from_addr_lower:
            return {
                "priority": "low",
                "is_spam": True,
                "spam_type": "promotional",
                "action": "archive",
                "reasons": [f"Promotional sender pattern: {pattern}"]
            }
    
    # Check for retail/marketing domains
    for domain in RETAIL_MARKETING_DOMAINS:
        if domain in from_addr_lower:
            # Check if it's a transactional email (order confirmation, shipping)
            transactional_keywords = [
                "order confirmation", "your order", "order #", "order number",
                "shipped", "tracking", "delivery", "has been delivered",
                "return", "refund", "receipt", "invoice", "payment",
                "account created", "password reset", "verify your"
            ]
            
            is_transactional = any(kw in subject_lower or kw in body_lower for kw in transactional_keywords)
            
            # If it's transactional, let it through
            if is_transactional:
                return {
                    "priority": "low",
                    "is_spam": False,
                    "spam_type": "not_spam",
                    "action": "read_only",
                    "reasons": ["Transactional email from retailer"]
                }
            else:
                # It's promotional marketing from a retailer
                return {
                    "priority": "low",
                    "is_spam": True,
                    "spam_type": "promotional",
                    "action": "archive",
                    "reasons": [f"Marketing email from retail domain: {domain}"]
                }
    
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
    
    # Scheduling / appointments / invites
    for keyword in SCHEDULING_KEYWORDS:
        if keyword in subject_lower or keyword in body_lower:
            return {
                "priority": "high",
                "is_spam": False,
                "action": "needs_reply",
                "reasons": [f"Scheduling/appointment keyword: {keyword}"]
            }

    # Time-sensitive requests
    for pattern in TIME_SENSITIVE_PATTERNS:
        if re.search(pattern, subject_lower) or re.search(pattern, body_lower):
            return {
                "priority": "high",
                "is_spam": False,
                "action": "needs_reply",
                "reasons": ["Time-sensitive request detected"]
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
