"""
Utility functions for the email agent.
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from .models import Email, Inference, Draft
from .rules import apply_heuristic_rules

logger = logging.getLogger(__name__)

def save_email_to_db(db: Session, email_data: Dict[str, Any]) -> Optional[Email]:
    """Save email data to database, handling duplicates by msg_id."""
    try:
        # Check if email already exists
        existing_email = db.query(Email).filter(Email.msg_id == email_data["msg_id"]).first()
        
        if existing_email:
            logger.info(f"Email with msg_id {email_data['msg_id']} already exists, skipping")
            return existing_email
        
        # Create new email record
        email = Email(
            msg_id=email_data["msg_id"],
            thread_id=email_data["thread_id"],
            from_addr=email_data["from_addr"],
            to_addr=email_data["to_addr"],
            subject=email_data["subject"],
            snippet=email_data["snippet"],
            raw_path=email_data["raw_path"],
            received_at=email_data.get("received_at"),
            labels_json=email_data.get("labels_json", {}),
            user_id=email_data.get("user_id")  # Set user_id from email_data
        )
        
        db.add(email)
        db.commit()
        db.refresh(email)
        
        logger.info(f"Saved new email: {email.subject[:50]}...")
        return email
        
    except Exception as e:
        logger.error(f"Error saving email to database: {e}")
        db.rollback()
        return None

def classify_with_rules_and_llm(db: Session, email: Email, llm_classify_func) -> Dict[str, Any]:
    """Apply heuristic rules first, then LLM if needed."""
    # Try heuristic rules first
    rule_result = apply_heuristic_rules(
        subject=email.subject,
        body=email.snippet,
        from_addr=email.from_addr
    )
    
    if rule_result:
        logger.info(f"Applied heuristic rules for email {email.id}")
        return rule_result
    
    # Fall back to LLM classification
    logger.info(f"Using LLM classification for email {email.id}")
    return llm_classify_func(email.subject, email.snippet)

def get_email_stats(db: Session) -> Dict[str, int]:
    """Get basic statistics about emails in the database."""
    total_emails = db.query(Email).count()
    
    # Count by classification - using text search for JSON fields
    high_priority = db.query(Inference).filter(
        Inference.kind == "classification",
        Inference.json.op('->>')('priority') == "high"
    ).count()
    
    needs_reply = db.query(Inference).filter(
        Inference.kind == "classification", 
        Inference.json.op('->>')('action') == "needs_reply"
    ).count()
    
    spam_count = db.query(Inference).filter(
        Inference.kind == "classification",
        Inference.json.op('->>')('is_spam') == "true"
    ).count()
    
    # Count drafts
    draft_count = db.query(Draft).filter(Draft.sent_at.is_(None)).count()
    
    return {
        "total_emails": total_emails,
        "high_priority": high_priority,
        "needs_reply": needs_reply,
        "spam": spam_count,
        "drafts": draft_count
    }

def format_email_for_display(email: Email, classification: Dict = None, summary: Dict = None) -> Dict[str, Any]:
    """Format email data for API display."""
    # Determine if email needs reply based on classification and replied status
    needs_reply = False
    if classification and classification.get('action') == 'needs_reply':
        # Only mark as needs_reply if user hasn't replied yet
        needs_reply = email.replied_at is None
    
    return {
        "id": email.id,
        "msg_id": email.msg_id,
        "from": email.from_addr,
        "to": email.to_addr,
        "subject": email.subject,
        "snippet": email.snippet[:200] + "..." if len(email.snippet) > 200 else email.snippet,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "is_read": email.is_read,
        "replied_at": email.replied_at.isoformat() if email.replied_at else None,
        "needs_reply": needs_reply,
        "classification": classification,
        "summary": summary
    }
