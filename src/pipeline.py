import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from .models import Email, Inference, Draft, DailyDigest, User
from .llm import classify_email, summarize_email, draft_reply, agent_route, daily_digest_summarize, rank_emails
from .utils import classify_with_rules_and_llm
from .config import settings

logger = logging.getLogger(__name__)

def process_email(db: Session, email: Email, classify_only: bool = False) -> bool:
    """Process a single email through the AI pipeline with ML spam detection.

    Args:
        db: Database session
        email: Email row to process
        classify_only: If True, perform only classification (LLM/ML). Skip summarization.
    """
    from .ml_spam_classifier import ml_classifier
    
    try:
        # Check if already processed (permanent caching - never reprocess)
        existing_classification = db.query(Inference).filter(
            and_(
                Inference.email_id == email.id,
                Inference.kind == "classification"
            )
        ).first()
        
        existing_summary = db.query(Inference).filter(
            and_(
                Inference.email_id == email.id,
                Inference.kind == "summary"
            )
        ).first()
        
        existing_ml_classification = db.query(Inference).filter(
            and_(
                Inference.email_id == email.id,
                Inference.kind == "ml_spam_classification"
            )
        ).first()
        
        if existing_classification and existing_summary and existing_ml_classification:
            logger.info(f"Email {email.id} already fully processed (cached), skipping")
            return True
        
        if existing_classification:
            logger.info(f"Email {email.id} already has classification (cached)")
        
        if existing_summary:
            logger.info(f"Email {email.id} already has summary (cached)")
        
        # Step 1: Classify email using heuristics first, then LLM fallback (skip if cached)
        if not existing_classification:
            logger.info(f"Classifying email {email.id}: {email.subject}")
            # Get user for sent email detection
            user = db.query(User).filter(User.id == email.user_id).first() if email.user_id else None
            
            # Fast-path: rules first, then LLM only if needed
            classification = classify_with_rules_and_llm(
                db=db,
                email=email,
                llm_classify_func=lambda subject, body: classify_email(subject, body, headers={}),
                user=user
            )
            
            # Save classification
            classification_inference = Inference(
                email_id=email.id,
                kind="classification",
                json=classification,
                model=settings.MODEL_NAME
            )
            db.add(classification_inference)
            db.commit()
        else:
            # Use cached classification
            classification = existing_classification.json
        
        # Step 2: ML-based spam classification (skip if cached)
        if not existing_ml_classification:
            logger.info(f"ML spam classification for email {email.id}")
            ml_result = ml_classifier.classify(
                email=email,
                db=db,
                user_id=email.user_id,
                snippet=email.snippet,
                llm_classification=classification
            )
            
            # Override LLM spam decision with ML if ML is more confident
            if ml_result['classification'] == 'spam':
                classification['is_spam'] = True
                classification['spam_type'] = 'spam'
            elif ml_result['classification'] == 'potential_spam':
                classification['is_spam'] = False  # Don't hide it completely
                classification['spam_type'] = 'potential_spam'
            else:
                classification['spam_type'] = 'not_spam'
            
            # Add ML score to classification
            classification['ml_spam_score'] = ml_result['ml_score']
            classification['ml_confidence'] = ml_result['confidence']
            
            # Save ML classification
            ml_inference = Inference(
                email_id=email.id,
                kind="ml_spam_classification",
                json=ml_result,
                model="ml_heuristic_v1"
            )
            db.add(ml_inference)
            
            # Update the original classification with ML insights
            if existing_classification:
                existing_classification.json = classification
            else:
                # Update the classification we just created
                classification_inference.json = classification
            
            db.commit()
        else:
            # Use cached ML classification
            ml_result = existing_ml_classification.json
            if 'spam_type' not in classification:
                classification['spam_type'] = ml_result.get('classification', 'not_spam')
        
        # Skip spam emails
        if classification.get("is_spam", False):
            logger.info(f"Email {email.id} marked as spam, skipping further processing")
            return True
        
        # Step 2: Summarize email (skip if cached). Only if not classify_only.
        # Gate: summarize only if likely useful (needs_reply or high priority)
        should_summarize = False
        if not classify_only and not existing_summary:
            try:
                action = classification.get("action") if isinstance(classification, dict) else None
                priority = classification.get("priority") if isinstance(classification, dict) else None
                should_summarize = (action == "needs_reply") or (priority == "high")
            except Exception:
                should_summarize = False

        if should_summarize:
            logger.info(f"Summarizing email {email.id}")
            summary = summarize_email(
                subject=email.subject,
                body=email.snippet,
                thread_context=""
            )
            
            # Save summary
            summary_inference = Inference(
                email_id=email.id,
                kind="summary",
                json=summary,
                model=settings.MODEL_NAME
            )
            db.add(summary_inference)
            db.commit()
        elif not classify_only and existing_summary:
            # Use cached summary
            summary = existing_summary.json
            logger.info(f"Using cached summary for email {email.id}")
        
        # Step 3: Draft replies - DISABLED (user must manually request drafts)
        # Drafts are now generated on-demand via /api/email/{email_id}/generate-drafts
        # if classification.get("action") == "needs_reply":
        #     logger.info(f"Drafting replies for email {email.id}")
        #     reply_options = draft_reply(
        #         subject=email.subject,
        #         body=email.snippet,
        #         summary=summary,
        #         signature=settings.DEFAULT_SIGNATURE
        #     )
        #     
        #     # Save reply options as drafts
        #     for i, option in enumerate(reply_options.get("options", [])):
        #         draft = Draft(
        #             email_id=email.id,
        #             draft_text=option.get("body", ""),
        #             confidence=90,  # Default confidence
        #             style=reply_options.get("style", "crisp")
        #         )
        #         db.add(draft)
        #     
        #     db.commit()
        #     logger.info(f"Created {len(reply_options.get('options', []))} draft replies for email {email.id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing email {email.id}: {e}")
        db.rollback()
        return False

def process_new_emails(db: Session, max_emails: int = None, target_non_spam: int = None, classify_only: bool = False) -> int:
    """
    Process unprocessed emails in the database.
    
    Args:
        db: Database session
        max_emails: Maximum number of emails to process (None = all)
        target_non_spam: Stop after processing this many non-spam emails (None = process all)
    
    Returns:
        Number of emails processed
    """
    # Find emails without BOTH classification and summary inferences
    # Get emails that have classifications
    emails_with_classification = db.query(Inference.email_id).filter(
        Inference.kind == "classification"
    ).distinct().subquery()
    
    # Get emails that have summaries
    emails_with_summary = db.query(Inference.email_id).filter(
        Inference.kind == "summary"
    ).distinct().subquery()
    
    # Find emails that are missing either classification or summary
    # Order by received_at DESC to process newest first
    unprocessed_emails = db.query(Email).filter(
        ~Email.id.in_(emails_with_classification) | ~Email.id.in_(emails_with_summary)
    ).order_by(Email.received_at.desc()).all()
    
    logger.info(f"Found {len(unprocessed_emails)} emails needing processing")
    
    if max_emails:
        logger.info(f"Limiting to {max_emails} emails")
    if target_non_spam:
        logger.info(f"Target: {target_non_spam} non-spam emails")
    
    processed_count = 0
    non_spam_count = 0
    
    for email in unprocessed_emails:
        # Check limits
        if max_emails and processed_count >= max_emails:
            logger.info(f"Reached max_emails limit ({max_emails}), stopping")
            break
        
        if target_non_spam and non_spam_count >= target_non_spam:
            logger.info(f"Reached target of {target_non_spam} non-spam emails, stopping")
            break
        
        # Check if this email already has both inferences (double-check to avoid race conditions)
        has_classification = db.query(Inference).filter(
            Inference.email_id == email.id,
            Inference.kind == "classification"
        ).first() is not None
        
        has_summary = db.query(Inference).filter(
            Inference.email_id == email.id,
            Inference.kind == "summary"
        ).first() is not None
        
        if has_classification and has_summary:
            logger.info(f"Email {email.id} already fully processed, skipping")
            continue
        
        if process_email(db, email, classify_only=classify_only):
            processed_count += 1
            
            # Check if this email is spam
            classification = db.query(Inference).filter(
                Inference.email_id == email.id,
                Inference.kind == "classification"
            ).first()
            
            if classification and not classification.json.get('is_spam', False):
                non_spam_count += 1
                logger.info(f"Non-spam count: {non_spam_count}/{target_non_spam if target_non_spam else '∞'}")
    
    logger.info(f"Processed {processed_count} emails ({non_spam_count} non-spam)")
    return processed_count


def summarize_pending_emails(db: Session, max_emails: int = None) -> int:
    """Summarize non-spam emails that are missing summaries.

    Runs sequentially; intended to be called in a background thread.
    """
    # Emails that already have summaries
    emails_with_summary = db.query(Inference.email_id).filter(
        Inference.kind == "summary"
    ).distinct().subquery()

    # Non-spam emails (from latest classification) and prioritize needs_reply/high
    classifications = db.query(Inference).filter(Inference.kind == "classification").all()
    non_spam_email_ids = [c.email_id for c in classifications if c.json and not c.json.get("is_spam", False)]
    priority_map = {c.email_id: (c.json.get("action"), c.json.get("priority")) for c in classifications if c.json}

    query = db.query(Email).filter(
        Email.id.in_(non_spam_email_ids),
        ~Email.id.in_(emails_with_summary)
    )

    # Prioritize needs_reply/high by sorting in Python after fetch
    emails = query.order_by(Email.received_at.desc()).all()
    def sort_key(e: Email):
        action, priority = priority_map.get(e.id, (None, None))
        is_needs = 1 if action == "needs_reply" else 0
        is_high = 1 if priority == "high" else 0
        # Higher score first
        return (is_needs, is_high, e.received_at)
    emails.sort(key=sort_key, reverse=True)

    if max_emails:
        emails = emails[:max_emails]
    count = 0
    for email in emails:
        try:
            logger.info(f"Background summarizing email {email.id}")
            summary = summarize_email(subject=email.subject, body=email.snippet, thread_context="")
            summary_inference = Inference(
                email_id=email.id,
                kind="summary",
                json=summary,
                model=settings.MODEL_NAME
            )
            db.add(summary_inference)
            db.commit()
            count += 1
        except Exception as e:
            logger.error(f"Failed to summarize email {email.id}: {e}")
            db.rollback()
    logger.info(f"Background summarized {count} emails")
    return count


def build_daily_digest(db: Session, user_id: int, digest_date):
    """Run the AI agent to produce a daily digest for a user and date.
    Separate sections: last 24 hours + unreplied emails needing response."""
    import datetime as dt
    from .utils import is_sent_by_user
    
    # Get user for filtering sent emails
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    now = dt.datetime.utcnow()
    last_24h = now - dt.timedelta(hours=24)
    
    # Get emails from the last 24 hours (excluding sent emails)
    recent_emails_raw = db.query(Email).filter(
        Email.user_id == user_id,
        Email.received_at >= last_24h
    ).all()
    
    recent_emails = [e for e in recent_emails_raw if not is_sent_by_user(e, user)]
    
    # Get unreplied emails that need a reply (regardless of age, excluding sent and recent)
    unreplied_emails = db.query(Email).filter(
        Email.user_id == user_id,
        Email.replied_at.is_(None)
    ).all()
    
    # Filter for those that need a reply based on classification and aren't sent by user
    unreplied_needing_response = []
    recent_email_ids = {e.id for e in recent_emails}
    
    for e in unreplied_emails:
        # Skip if sent by user
        if is_sent_by_user(e, user):
            continue
        # Skip if already in recent emails (to avoid duplication)
        if e.id in recent_email_ids:
            continue
        
        cls = db.query(Inference).filter(
            and_(Inference.email_id == e.id, Inference.kind == "classification")
        ).order_by(Inference.created_at.desc()).first()
        if cls and cls.json.get("action") == "needs_reply":
            unreplied_needing_response.append(e)
    
    # Sort both lists
    recent_emails.sort(key=lambda e: e.received_at or dt.datetime.min, reverse=True)
    unreplied_needing_response.sort(key=lambda e: e.received_at or dt.datetime.min, reverse=True)

    # Helper to create item from email
    def email_to_item(e):
        cls = db.query(Inference).filter(
            and_(Inference.email_id == e.id, Inference.kind == "classification")
        ).order_by(Inference.created_at.desc()).first()
        summ = db.query(Inference).filter(
            and_(Inference.email_id == e.id, Inference.kind == "summary")
        ).order_by(Inference.created_at.desc()).first()
        class_json = cls.json if cls else None
        summ_json = summ.json if summ else None
        link = f"/api/email/{e.id}"
        return {
            "email_id": e.id,
            "subject": e.subject,
            "from": e.from_addr,
            "received_at": e.received_at.isoformat() if e.received_at else None,
            "importance": (class_json or {}).get("priority"),
            "action": (class_json or {}).get("action"),
            "is_spam": (class_json or {}).get("is_spam", False),
            "summary": (summ_json or {}).get("summary"),
            "link": link
        }
    
    # Create separate item lists
    recent_items = [email_to_item(e) for e in recent_emails[:10]]  # Limit to 10 most recent
    needs_reply_items = [email_to_item(e) for e in unreplied_needing_response[:10]]  # Limit to 10
    
    # Filter out spam from both
    recent_items = [i for i in recent_items if not i.get("is_spam")]
    needs_reply_items = [i for i in needs_reply_items if not i.get("is_spam")]
    
    # Basic stats
    stats = {
        "recent_count": len(recent_items),
        "needs_reply_count": len(needs_reply_items),
        "total": len(recent_items) + len(needs_reply_items)
    }

    # Generate summaries for both sections
    recent_summary = None
    needs_reply_summary = None
    
    if recent_items:
        recent_summary = daily_digest_summarize({
            "stats": {"count": len(recent_items)},
            "top_items": recent_items,
            "section": "recent_24h"
        })
    
    if needs_reply_items:
        needs_reply_summary = daily_digest_summarize({
            "stats": {"count": len(needs_reply_items)},
            "top_items": needs_reply_items,
            "section": "needs_reply"
        })

    payload = {
        "recent_24h": {
            "overview": recent_summary.get("overview", "No new emails in the last 24 hours") if recent_summary else "No new emails in the last 24 hours",
            "items": recent_items,
            "count": len(recent_items)
        },
        "needs_reply": {
            "overview": needs_reply_summary.get("overview", "No emails waiting for reply") if needs_reply_summary else "No emails waiting for reply",
            "items": needs_reply_items,
            "count": len(needs_reply_items)
        },
        "stats": stats
    }

    # Upsert DailyDigest
    existing = db.query(DailyDigest).filter(
        DailyDigest.user_id == user_id,
        DailyDigest.digest_date == digest_date
    ).first()
    if existing:
        existing.summary_json = payload
        existing.updated_at = dt.datetime.utcnow()
        db.commit()
        return existing
    else:
        dd = DailyDigest(user_id=user_id, digest_date=digest_date, summary_json=payload)
        db.add(dd)
        db.commit()
        db.refresh(dd)
        return dd

def get_email_with_inferences(db: Session, email_id: int) -> dict:
    """Get an email with all its inferences and drafts."""
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        return None
    
    # Get latest inferences
    classification = db.query(Inference).filter(
        and_(
            Inference.email_id == email_id,
            Inference.kind == "classification"
        )
    ).order_by(Inference.created_at.desc()).first()
    
    summary = db.query(Inference).filter(
        and_(
            Inference.email_id == email_id,
            Inference.kind == "summary"
        )
    ).order_by(Inference.created_at.desc()).first()
    
    # Get drafts
    drafts = db.query(Draft).filter(
        and_(
            Draft.email_id == email_id,
            Draft.sent_at.is_(None)  # Only unsent drafts
        )
    ).all()
    
    return {
        "email": email,
        "classification": classification.json if classification else None,
        "summary": summary.json if summary else None,
        "drafts": drafts
    }
