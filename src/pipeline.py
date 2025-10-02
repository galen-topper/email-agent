import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from .models import Email, Inference, Draft
from .llm import classify_email, summarize_email, draft_reply
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
            # Fast-path: rules first, then LLM only if needed
            classification = classify_with_rules_and_llm(
                db=db,
                email=email,
                llm_classify_func=lambda subject, body: classify_email(subject, body, headers={})
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
