from fastapi import FastAPI, HTTPException, Depends, Query, Cookie, Response, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Optional
import logging
from datetime import datetime
from pathlib import Path

from .config import settings
from .models import Base, Email, Inference, Draft, User, ComposedDraft
from .imap_client import fetch_unseen_emails
from .pipeline import process_email, process_new_emails, get_email_with_inferences
from .smtp_client import send_reply
from .utils import save_email_to_db, get_email_stats, format_email_for_display
from . import auth

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
engine = create_engine(settings.DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base.metadata.create_all(engine)

# FastAPI app
app = FastAPI(
    title="AgentMail",
    description="AI-powered email triage and reply system",
    version="1.0.0"
)

# Mount static files
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory=str(templates_dir))

def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    session_token: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get the current logged-in user."""
    if not session_token:
        return None
    return auth.get_current_user(db, session_token)

def require_auth(current_user: Optional[User] = Depends(get_current_user)) -> User:
    """Require authentication for an endpoint."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return current_user

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat(),
        "oauth_configured": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "openai_configured": bool(settings.OPENAI_API_KEY)
    }

@app.get("/api/background-status")
def get_background_status(current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Check if there are unprocessed emails being worked on in the background (requires auth)."""
    # Count emails without classifications
    unprocessed = db.query(Email).outerjoin(
        Inference, 
        (Email.id == Inference.email_id) & (Inference.kind == "classification")
    ).filter(
        Email.user_id == current_user.id,
        Inference.id == None
    ).count()
    
    # Count total emails
    total_emails = db.query(Email).filter(Email.user_id == current_user.id).count()
    processed_emails = total_emails - unprocessed
    
    return {
        "unprocessed": unprocessed,
        "total": total_emails,
        "processed": processed_emails,
        "is_processing": unprocessed > 0
    }

@app.get("/config-status")
def config_status():
    """Check if email configuration is properly set up."""
    # Check if required environment variables are set
    is_configured = (
        settings.IMAP_USER and 
        settings.IMAP_PASS and 
        settings.IMAP_USER != "you@gmail.com" and
        settings.IMAP_PASS != "app_password_or_oauth_token" and
        settings.OPENAI_API_KEY and
        settings.OPENAI_API_KEY != "your_openai_api_key_here"
    )
    
    return {
        "is_configured": is_configured,
        "has_imap": bool(settings.IMAP_USER and settings.IMAP_USER != "you@gmail.com"),
        "has_openai": bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your_openai_api_key_here"),
        "message": "Configuration is complete" if is_configured else "Please configure your .env file with email and OpenAI credentials"
    }

@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get email statistics."""
    return get_email_stats(db)

@app.get("/api/inbox")
def get_inbox(
    filter: Optional[str] = Query(None, alias="filter", description="Filter by: needs_reply, high, normal, low"),
    limit: int = Query(20, description="Number of emails per page (10, 20, 50, or 100)"),
    offset: int = Query(0, description="Number of emails to skip (for pagination)"),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get inbox emails with optional filtering and pagination (API endpoint, requires auth). Excludes spam by default."""
    logger.info(f"GET /api/inbox - user: {current_user.email}, filter: {filter}, limit: {limit}, offset: {offset}")
    
    # Filter emails by current user
    base_query = db.query(Email).filter(Email.user_id == current_user.id)
    
    # Exclude spam emails from inbox by default (but NOT potential spam)
    # Get all classifications and filter in Python (more reliable than JSON queries)
    all_classifications = db.query(Inference).filter(Inference.kind == "classification").all()
    spam_email_ids = [c.email_id for c in all_classifications if c.json and c.json.get('is_spam') == True]
    
    # Don't exclude potential_spam from inbox - they stay visible with warning
    if spam_email_ids:
        base_query = base_query.filter(~Email.id.in_(spam_email_ids))
    
    # Get all emails first (ordered by date)
    all_emails = base_query.order_by(Email.received_at.desc()).all()
    logger.info(f"Total non-spam emails for user: {len(all_emails)}")
    
    # Apply filter if specified
    if filter and filter in ["needs_reply", "high", "normal", "low"]:
        filtered_emails = []
        
        for email in all_emails:
            # Get latest classification
            classification = db.query(Inference).filter(
                Inference.email_id == email.id,
                Inference.kind == "classification"
            ).order_by(Inference.created_at.desc()).first()
            
            if classification:
                class_data = classification.json
                if filter == "needs_reply" and class_data.get("action") == "needs_reply":
                    filtered_emails.append(email)
                elif filter in ["high", "normal", "low"] and class_data.get("priority") == filter:
                    filtered_emails.append(email)
            elif filter == "needs_reply":  # Include unprocessed emails in needs_reply filter
                filtered_emails.append(email)
        
        emails = filtered_emails
        logger.info(f"Filtered to {len(emails)} emails for filter '{filter}'")
    else:
        emails = all_emails
    
    # Get total count after filtering
    total_count = len(emails)
    
    # Apply pagination AFTER filtering
    emails = emails[offset:offset + limit]
    
    # Format emails for display
    result = []
    for email in emails:
        # Get latest classification and summary
        classification = db.query(Inference).filter(
            Inference.email_id == email.id,
            Inference.kind == "classification"
        ).order_by(Inference.created_at.desc()).first()
        
        summary = db.query(Inference).filter(
            Inference.email_id == email.id,
            Inference.kind == "summary"
        ).order_by(Inference.created_at.desc()).first()
        
        result.append(format_email_for_display(
            email,
            classification.json if classification else None,
            summary.json if summary else None
        ))
    
    return {
        "emails": result, 
        "count": len(result),
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(result) < total_count
    }

@app.get("/api/spam")
def get_spam(
    spam_type: str = Query("spam", description="Type: spam or potential_spam"),
    limit: int = Query(20, description="Number of emails per page (10, 20, 50, or 100)"),
    offset: int = Query(0, description="Number of emails to skip (for pagination)"),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get spam or potential spam emails with pagination (API endpoint, requires auth)."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Filter emails by current user
    base_query = db.query(Email).filter(Email.user_id == current_user.id)
    
    # Get classifications
    all_classifications = db.query(Inference).filter(Inference.kind == "classification").all()
    
    # Filter by spam type
    if spam_type == "potential_spam":
        # Get emails marked as potential_spam
        email_ids = [
            c.email_id for c in all_classifications 
            if c.json and c.json.get('spam_type') == 'potential_spam'
        ]
        logger.info(f"Found {len(email_ids)} potential spam emails for user {current_user.id}")
    else:
        # Get emails marked as spam (is_spam=True)
        email_ids = [
            c.email_id for c in all_classifications 
            if c.json and c.json.get('is_spam') == True
        ]
        logger.info(f"Found {len(email_ids)} spam emails for user {current_user.id}")
    
    if email_ids:
        base_query = base_query.filter(Email.id.in_(email_ids))
    else:
        # No spam found, return empty result
        logger.info(f"No {spam_type} emails found, returning empty result")
        base_query = base_query.filter(Email.id == -1)
    
    # Get total count for pagination
    total_count = base_query.count()
    
    # Apply ordering, limit, and offset
    query = base_query.order_by(Email.received_at.desc()).limit(limit).offset(offset)
    
    emails = query.all()
    
    # For each email, get the latest classification and summary
    result = []
    for email in emails:
        classification = db.query(Inference).filter(
            Inference.email_id == email.id,
            Inference.kind == "classification"
        ).order_by(Inference.created_at.desc()).first()
        
        summary = db.query(Inference).filter(
            Inference.email_id == email.id,
            Inference.kind == "summary"
        ).order_by(Inference.created_at.desc()).first()
        
        result.append((
            email,
            classification.json if classification else None,
            summary.json if summary else None
        ))
    
    return {
        "emails": result, 
        "count": len(result),
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(result) < total_count
    }

@app.get("/api/email/{email_id}")
def get_email_detail(email_id: int, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Get detailed email information including inferences and drafts (requires auth)."""
    email_data = get_email_with_inferences(db, email_id)
    
    if not email_data:
        raise HTTPException(status_code=404, detail="Email not found")
    
    email = email_data["email"]
    classification = email_data["classification"]
    summary = email_data["summary"]
    drafts = email_data["drafts"]
    
    return {
        "email": format_email_for_display(email, classification, summary),
        "classification": classification,
        "summary": summary,
        "drafts": [
            {
                "id": draft.id,
                "draft_text": draft.draft_text,
                "confidence": draft.confidence,
                "style": draft.style,
                "created_at": draft.created_at.isoformat()
            }
            for draft in drafts
        ]
    }

@app.post("/api/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Approve and send a draft reply (requires auth)."""
    draft = db.query(Draft).filter(Draft.id == draft_id).first()
    
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    if draft.sent_at:
        raise HTTPException(status_code=400, detail="Draft already sent")
    
    # Get the original email
    email = db.query(Email).filter(Email.id == draft.email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Original email not found")
    
    # Send the reply
    success = send_reply(email, draft.draft_text)
    
    if success:
        # Mark draft as sent
        draft.sent_at = datetime.utcnow()
        draft.approved_at = datetime.utcnow()
        db.commit()
        
        return {"status": "sent", "message": "Reply sent successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send reply")

@app.post("/api/email/{email_id}/reclassify")
def reclassify_email(email_id: int, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Force reclassification of an email (requires auth)."""
    email = db.query(Email).filter(Email.id == email_id).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Process the email again
    success = process_email(db, email)
    
    if success:
        return {"status": "success", "message": "Email reclassified"}
    else:
        raise HTTPException(status_code=500, detail="Failed to reclassify email")

@app.post("/api/send-email")
def send_email_endpoint(
    email_data: dict,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Send an email via Gmail API (requires auth)."""
    from .smtp_client import send_email_smtp
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        to_addr = email_data.get('to', '')
        cc_addr = email_data.get('cc', '')
        bcc_addr = email_data.get('bcc', '')
        subject = email_data.get('subject', '')
        body = email_data.get('body', '')
        
        if not to_addr or not subject or not body:
            raise HTTPException(status_code=400, detail="Missing required fields: to, subject, body")
        
        logger.info(f"Sending email to {to_addr} from {current_user.email}")
        
        # Send via Gmail API
        success = send_email_smtp(
            to_addr=to_addr,
            subject=subject,
            body=body,
            cc_addr=cc_addr if cc_addr else None,
            bcc_addr=bcc_addr if bcc_addr else None,
            user=current_user
        )
        
        if success:
            # Mark draft as sent if draft_id provided
            draft_id = email_data.get('draft_id')
            if draft_id:
                draft = db.query(ComposedDraft).filter(
                    ComposedDraft.id == draft_id,
                    ComposedDraft.user_id == current_user.id
                ).first()
                if draft:
                    draft.sent_at = datetime.utcnow()
                    
                    # If this was a reply, mark the original email as replied
                    if draft.is_reply and draft.reply_to_email_id:
                        original_email = db.query(Email).filter(Email.id == draft.reply_to_email_id).first()
                        if original_email:
                            original_email.replied_at = datetime.utcnow()
                    
                    db.commit()
            
            return {"status": "success", "message": "Email sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send email via Gmail API")
            
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.get("/api/contacts")
def get_contacts(
    query: Optional[str] = Query(None, description="Search query to filter contacts"),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get user's contacts from Gmail (People API + email history)."""
    from . import gmail_api_client
    
    try:
        contacts = gmail_api_client.fetch_user_contacts(current_user, query=query, max_results=50)
        return {"contacts": contacts}
    except Exception as e:
        logger.error(f"Failed to fetch contacts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch contacts: {str(e)}")

@app.post("/api/email/{email_id}/generate-drafts")
def generate_drafts(email_id: int, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Generate draft replies for an email on-demand (requires auth)."""
    from .llm import draft_reply
    
    email = db.query(Email).filter(Email.id == email_id, Email.user_id == current_user.id).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Check if drafts already exist
    existing_drafts = db.query(Draft).filter(Draft.email_id == email_id).all()
    if existing_drafts:
        return {
            "status": "exists",
            "message": "Drafts already exist for this email",
            "draft_count": len(existing_drafts)
        }
    
    try:
        # Get the summary for context
        summary_inference = db.query(Inference).filter(
            Inference.email_id == email_id,
            Inference.kind == "summary"
        ).order_by(Inference.created_at.desc()).first()
        
        summary = summary_inference.json if summary_inference else {}
        
        # Generate draft replies
        logger.info(f"Generating drafts for email {email.id}")
        reply_options = draft_reply(
            subject=email.subject,
            body=email.snippet,
            summary=summary,
            signature=settings.DEFAULT_SIGNATURE
        )
        
        # Save reply options as drafts
        draft_count = 0
        for i, option in enumerate(reply_options.get("options", [])):
            draft = Draft(
                email_id=email.id,
                draft_text=option.get("body", ""),
                confidence=90,  # Default confidence
                style=reply_options.get("style", "crisp")
            )
            db.add(draft)
            draft_count += 1
        
        db.commit()
        logger.info(f"Created {draft_count} draft replies for email {email.id}")
        
        return {
            "status": "success",
            "message": f"Generated {draft_count} draft replies",
            "draft_count": draft_count
        }
        
    except Exception as e:
        logger.error(f"Failed to generate drafts for email {email_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate drafts: {str(e)}")

# Global flag to cancel background sync
background_sync_cancelled = {}

@app.post("/api/poll")
def manual_poll(current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Smart sync - only fetches NEW emails and processes them quickly (requires auth)."""
    try:
        from .gmail_api_client import fetch_user_emails
        import threading
        
        # Reset cancel flag for this user
        background_sync_cancelled[current_user.id] = False
        
        # Check how many emails user already has
        existing_count = db.query(Email).filter(Email.user_id == current_user.id).count()
        
        logger.info(f"User {current_user.email} has {existing_count} emails in database")
        
        if existing_count == 0:
            # First sync - fetch initial batch (20 emails) and process quickly
            logger.info("First sync detected - fetching initial 20 emails")
            
            def save_callback(email_data):
                save_email_to_db(db, email_data)
            
            fetched_emails = fetch_user_emails(current_user, save_callback, max_results=20)
            
            # Process just enough to get ~20 non-spam emails for display
            processed_count = process_new_emails(db, target_non_spam=20)
            
            # Start background thread to fetch and process more emails
            def background_fetch():
                from sqlalchemy.orm import Session as SessionClass
                bg_db = SessionClass(bind=db.get_bind())
                
                try:
                    logger.info("Background fetch started - fetching up to 480 more emails")
                    
                    if background_sync_cancelled.get(current_user.id, False):
                        logger.info("Background sync cancelled by user")
                        return
                    
                    def bg_save_callback(email_data):
                        if background_sync_cancelled.get(current_user.id, False):
                            return
                        save_email_to_db(bg_db, email_data)
                    
                    more_emails = fetch_user_emails(current_user, bg_save_callback, max_results=480)
                    logger.info(f"Background fetch completed - fetched {len(more_emails)} more emails")
                    
                    if background_sync_cancelled.get(current_user.id, False):
                        logger.info("Background sync cancelled by user before processing")
                        return
                    
                    bg_processed = process_new_emails(bg_db)
                    logger.info(f"Background processing completed - processed {bg_processed} emails")
                    
                except Exception as e:
                    logger.error(f"Background fetch error: {e}")
                finally:
                    bg_db.close()
            
            thread = threading.Thread(target=background_fetch, daemon=True)
            thread.start()
            
            return {
                "status": "success",
                "fetched": len(fetched_emails),
                "processed": processed_count,
                "background_processing": True,
                "message": "First sync - fetching more in background",
                "error": None
            }
        else:
            # Regular sync - only fetch NEW emails (check first 50 for new ones)
            logger.info("Regular sync - checking for new emails")
            
            new_email_count = 0
            
            def save_callback(email_data):
                nonlocal new_email_count
                email = save_email_to_db(db, email_data)
                # save_email_to_db returns Email object if new, None if already exists
                if email is not None:
                    new_email_count += 1
            
            # Fetch only the 50 most recent emails from Gmail
            # save_email_to_db will skip duplicates
            fetched = fetch_user_emails(current_user, save_callback, max_results=50)
            
            logger.info(f"Checked 50 most recent emails, found {new_email_count} new emails")
            
            # Process ONLY the new emails quickly
            if new_email_count > 0:
                # Get the newest unprocessed emails
                processed_count = process_new_emails(db, max_emails=new_email_count)
                logger.info(f"Processed {processed_count} new emails")
                
                return {
                    "status": "success",
                    "fetched": new_email_count,
                    "processed": processed_count,
                    "background_processing": False,
                    "message": f"Found {new_email_count} new email(s)",
                    "error": None
                }
            else:
                return {
                    "status": "success",
                    "fetched": 0,
                    "processed": 0,
                    "background_processing": False,
                    "message": "No new emails",
                    "error": None
                }
        
    except Exception as e:
        logger.error(f"Manual poll failed: {e}")
        error_msg = str(e)
        
        # Provide helpful error messages
        if "authentication" in error_msg.lower() or "login" in error_msg.lower():
            error_msg = "Authentication failed. Please log out and log in again."
        elif "connection" in error_msg.lower() or "network" in error_msg.lower():
            error_msg = "Connection failed. Check your internet connection."
        
        return {
            "status": "error",
            "fetched": 0,
            "processed": 0,
            "error": error_msg
        }

@app.post("/api/cancel-sync")
def cancel_sync(current_user: User = Depends(require_auth)):
    """Cancel the current background sync for the user."""
    background_sync_cancelled[current_user.id] = True
    logger.info(f"User {current_user.email} cancelled background sync")
    return {"status": "success", "message": "Background sync cancelled"}

@app.post("/api/drafts/save")
def save_draft(
    draft_data: dict,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Save or update a composed draft (auto-save)."""
    try:
        draft_id = draft_data.get('id')
        to_addr = draft_data.get('to', '').strip()
        cc_addr = draft_data.get('cc', '').strip()
        bcc_addr = draft_data.get('bcc', '').strip()
        subject = draft_data.get('subject', '').strip()
        body = draft_data.get('body', '').strip()
        reply_to_email_id = draft_data.get('reply_to_email_id')
        is_reply = draft_data.get('is_reply', False)
        is_forward = draft_data.get('is_forward', False)
        
        # Don't save completely empty drafts
        if not to_addr and not subject and not body:
            return {"status": "skipped", "message": "Empty draft not saved"}
        
        # Update existing draft or create new one
        if draft_id:
            draft = db.query(ComposedDraft).filter(
                ComposedDraft.id == draft_id,
                ComposedDraft.user_id == current_user.id
            ).first()
            
            if draft:
                draft.to_addr = to_addr
                draft.cc_addr = cc_addr if cc_addr else None
                draft.bcc_addr = bcc_addr if bcc_addr else None
                draft.subject = subject
                draft.body = body
                draft.updated_at = datetime.utcnow()
            else:
                return {"status": "error", "message": "Draft not found"}
        else:
            # Create new draft
            draft = ComposedDraft(
                user_id=current_user.id,
                to_addr=to_addr,
                cc_addr=cc_addr if cc_addr else None,
                bcc_addr=bcc_addr if bcc_addr else None,
                subject=subject,
                body=body,
                reply_to_email_id=reply_to_email_id,
                is_reply=is_reply,
                is_forward=is_forward
            )
            db.add(draft)
        
        db.commit()
        db.refresh(draft)
        
        logger.info(f"Saved draft {draft.id} for user {current_user.email}")
        
        return {
            "status": "success",
            "draft_id": draft.id,
            "message": "Draft saved"
        }
        
    except Exception as e:
        logger.error(f"Failed to save draft: {e}")
        db.rollback()
        return {"status": "error", "message": str(e)}

@app.get("/api/drafts")
def get_drafts(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get all unsent drafts for the current user (includes Gmail drafts)."""
    from . import gmail_api_client
    
    try:
        # Fetch local drafts from database
        local_drafts = db.query(ComposedDraft).filter(
            ComposedDraft.user_id == current_user.id,
            ComposedDraft.sent_at.is_(None)
        ).order_by(ComposedDraft.updated_at.desc()).all()
        
        # Fetch Gmail drafts
        gmail_drafts = gmail_api_client.fetch_gmail_drafts(current_user)
        
        # Sync Gmail drafts into database (avoid duplicates by gmail_draft_id)
        for gmail_draft in gmail_drafts:
            gmail_draft_id = gmail_draft.get('gmail_draft_id')
            
            # Check if this Gmail draft already exists in our database
            existing = db.query(ComposedDraft).filter(
                ComposedDraft.user_id == current_user.id,
                ComposedDraft.gmail_draft_id == gmail_draft_id
            ).first()
            
            if not existing:
                # Create new draft from Gmail
                new_draft = ComposedDraft(
                    user_id=current_user.id,
                    gmail_draft_id=gmail_draft_id,
                    to_addr=gmail_draft.get('to_addr', ''),
                    cc_addr=gmail_draft.get('cc_addr'),
                    bcc_addr=gmail_draft.get('bcc_addr'),
                    subject=gmail_draft.get('subject', ''),
                    body=gmail_draft.get('body', ''),
                    is_reply=gmail_draft.get('is_reply', False),
                    is_forward=gmail_draft.get('is_forward', False)
                )
                db.add(new_draft)
                logger.info(f"Imported Gmail draft {gmail_draft_id} for user {current_user.email}")
        
        db.commit()
        
        # Re-fetch all drafts after sync
        all_drafts = db.query(ComposedDraft).filter(
            ComposedDraft.user_id == current_user.id,
            ComposedDraft.sent_at.is_(None)
        ).order_by(ComposedDraft.updated_at.desc()).all()
        
        result = []
        for draft in all_drafts:
            result.append({
                "id": draft.id,
                "to": draft.to_addr,
                "cc": draft.cc_addr,
                "bcc": draft.bcc_addr,
                "subject": draft.subject,
                "body": draft.body,
                "is_reply": draft.is_reply,
                "is_forward": draft.is_forward,
                "reply_to_email_id": draft.reply_to_email_id,
                "gmail_draft_id": draft.gmail_draft_id,
                "created_at": draft.created_at.isoformat() if draft.created_at else None,
                "updated_at": draft.updated_at.isoformat() if draft.updated_at else None
            })
        
        return {"drafts": result}
        
    except Exception as e:
        logger.error(f"Failed to get drafts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/drafts/{draft_id}")
def delete_draft(
    draft_id: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete a draft."""
    try:
        draft = db.query(ComposedDraft).filter(
            ComposedDraft.id == draft_id,
            ComposedDraft.user_id == current_user.id
        ).first()
        
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        
        db.delete(draft)
        db.commit()
        
        return {"status": "success", "message": "Draft deleted"}
        
    except Exception as e:
        logger.error(f"Failed to delete draft: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/drafts/{draft_id}")
def get_draft(
    draft_id: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get a specific draft by ID."""
    try:
        draft = db.query(ComposedDraft).filter(
            ComposedDraft.id == draft_id,
            ComposedDraft.user_id == current_user.id
        ).first()
        
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        
        return {
            "id": draft.id,
            "to": draft.to_addr,
            "cc": draft.cc_addr,
            "bcc": draft.bcc_addr,
            "subject": draft.subject,
            "body": draft.body,
            "is_reply": draft.is_reply,
            "is_forward": draft.is_forward,
            "reply_to_email_id": draft.reply_to_email_id,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
            "updated_at": draft.updated_at.isoformat() if draft.updated_at else None
        }
        
    except Exception as e:
        logger.error(f"Failed to get draft: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/email/{email_id}/mark-read")
def mark_email_read(
    email_id: int,
    read_status: dict,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Mark an email as read or unread (syncs with Gmail)."""
    from . import gmail_api_client
    
    try:
        email = db.query(Email).filter(
            Email.id == email_id,
            Email.user_id == current_user.id
        ).first()
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        is_read = read_status.get('is_read', True)
        
        # Update in local database
        email.is_read = is_read
        db.commit()
        
        # Sync with Gmail (mark as read/unread there too)
        gmail_api_client.mark_email_as_read_in_gmail(current_user, email.msg_id, is_read)
        
        return {"status": "success", "is_read": is_read}
        
    except Exception as e:
        logger.error(f"Failed to mark email as read: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/email/{email_id}/spam-feedback")
def mark_spam_feedback(
    email_id: int,
    feedback_data: dict,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Record user feedback on spam classification for ML training."""
    from .ml_spam_classifier import ml_classifier
    from .models import SpamFeedback
    
    try:
        email = db.query(Email).filter(
            Email.id == email_id,
            Email.user_id == current_user.id
        ).first()
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        is_spam = feedback_data.get('is_spam', False)
        
        # Extract features for ML training
        features = ml_classifier.extract_features(email, email.snippet)
        
        # Get current classification
        classification_inference = db.query(Inference).filter(
            and_(
                Inference.email_id == email.id,
                Inference.kind == "classification"
            )
        ).first()
        
        llm_classification = classification_inference.json if classification_inference else None
        
        # Record feedback
        ml_classifier.record_feedback(
            db=db,
            email=email,
            user_id=current_user.id,
            is_spam=is_spam,
            features=features,
            llm_classification=llm_classification
        )
        
        # Update classification immediately based on feedback
        if classification_inference:
            classification = classification_inference.json
            if is_spam:
                classification['is_spam'] = True
                classification['spam_type'] = 'spam'
            else:
                classification['is_spam'] = False
                classification['spam_type'] = 'not_spam'
            classification_inference.json = classification
            db.commit()
        
        logger.info(f"Recorded spam feedback for email {email_id}: is_spam={is_spam}")
        
        return {
            "status": "success",
            "message": "Feedback recorded - future emails will be classified more accurately"
        }
        
    except Exception as e:
        logger.error(f"Failed to record spam feedback: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reclassify-all")
def reclassify_all_emails(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Reclassify all emails with updated aggressive spam detection rules."""
    from .pipeline import process_email
    
    try:
        # Get all user's emails
        emails = db.query(Email).filter(Email.user_id == current_user.id).all()
        
        logger.info(f"Starting reclassification of {len(emails)} emails for user {current_user.email}")
        
        # Delete all existing classifications and ML classifications to force reprocessing
        deleted_count = db.query(Inference).filter(
            and_(
                Inference.email_id.in_([e.id for e in emails]),
                or_(
                    Inference.kind == "classification",
                    Inference.kind == "ml_spam_classification"
                )
            )
        ).delete(synchronize_session=False)
        
        db.commit()
        logger.info(f"Deleted {deleted_count} old classifications")
        
        # Reprocess all emails with new rules
        processed = 0
        for email in emails:
            try:
                process_email(db, email)
                processed += 1
                if processed % 10 == 0:
                    logger.info(f"Reclassified {processed}/{len(emails)} emails")
            except Exception as e:
                logger.error(f"Failed to reclassify email {email.id}: {e}")
                continue
        
        logger.info(f"Reclassification complete: {processed}/{len(emails)} emails processed")
        
        return {
            "status": "success",
            "total_emails": len(emails),
            "processed": processed,
            "message": f"Reclassified {processed} emails with updated spam detection rules"
        }
        
    except Exception as e:
        logger.error(f"Reclassification failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Root route - redirect to login or inbox
@app.get("/")
def root(current_user: Optional[User] = Depends(get_current_user)):
    """Redirect to login or inbox based on authentication status."""
    if current_user:
        return RedirectResponse(url="/inbox")
    return RedirectResponse(url="/login")

# Login page
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: Optional[str] = Query(None)):
    """Display the login page."""
    oauth_url = None
    try:
        if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
            oauth_url, state = auth.get_authorization_url()
    except Exception as e:
        import traceback
        logger.error(f"Failed to get OAuth URL: {e}")
        logger.error(traceback.format_exc())
        error = f"OAuth configuration error: {str(e)}"
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "oauth_url": oauth_url,
        "error": error
    })

# OAuth callback
@app.get("/auth/callback")
def auth_callback(
    code: str,
    state: str,
    response: Response,
    db: Session = Depends(get_db)
):
    """Handle OAuth callback from Google."""
    try:
        # Exchange code for tokens
        user_data = auth.exchange_code_for_tokens(code, state)
        
        # Create or update user
        user = auth.create_or_update_user(db, user_data)
        
        # Create session token
        session_token = auth.create_session_token(user.id)
        
        # Set cookie
        response = RedirectResponse(url="/inbox")
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=session_token,
            httponly=True,
            max_age=86400 * 7,  # 7 days
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        import traceback
        error_detail = str(e)
        logger.error(f"OAuth callback failed: {error_detail}")
        logger.error(traceback.format_exc())
        # URL encode the error message
        from urllib.parse import quote
        return RedirectResponse(url=f"/login?error={quote(error_detail)}")

# Logout
@app.post("/auth/logout")
def logout(response: Response):
    """Logout the current user."""
    response = RedirectResponse(url="/login")
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return response

# Inbox page (protected) - with redirect to login if not authenticated
@app.get("/inbox", response_class=HTMLResponse)
async def inbox_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Display the inbox for the logged-in user, redirect to login if not authenticated."""
    if not current_user:
        return RedirectResponse(url="/login")
    
    index_file = templates_dir / "index.html"
    with open(index_file, 'r') as f:
        return f.read()

# Legacy inline HTML (kept for reference, remove if not needed)
@app.get("/legacy", response_class=HTMLResponse)
def get_legacy_frontend():
    """Legacy inline HTML frontend."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Email Agent</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .email { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }
            .email.high { border-left: 5px solid #ff4444; }
            .email.normal { border-left: 5px solid #44aa44; }
            .email.low { border-left: 5px solid #888; }
            .email.spam { border-left: 5px solid #ffaa00; background: #fff8e1; }
            .draft { background: #f0f8ff; padding: 10px; margin: 5px 0; border-radius: 3px; }
            .approve-btn { background: #4CAF50; color: white; padding: 5px 10px; border: none; border-radius: 3px; cursor: pointer; }
            .approve-btn:hover { background: #45a049; }
            .filter-btn { margin: 5px; padding: 8px 15px; border: 1px solid #ddd; background: white; cursor: pointer; }
            .filter-btn.active { background: #007bff; color: white; }
        </style>
    </head>
    <body>
        <h1>Email Agent Dashboard</h1>
        
        <div>
            <button class="filter-btn active" onclick="loadInbox()">All</button>
            <button class="filter-btn" onclick="loadInbox('needs_reply')">Needs Reply</button>
            <button class="filter-btn" onclick="loadInbox('high')">High Priority</button>
            <button class="filter-btn" onclick="loadInbox('spam')">Spam</button>
            <button class="filter-btn" onclick="pollEmails()">Fetch New</button>
        </div>
        
        <div id="emails"></div>
        
        <script>
            let currentFilter = null;
            
            async function loadInbox(filter = null) {
                currentFilter = filter;
                document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');
                
                const url = filter ? `/inbox?filter=${filter}` : '/inbox';
                const response = await fetch(url);
                const data = await response.json();
                
                displayEmails(data.emails);
            }
            
            function displayEmails(emails) {
                const container = document.getElementById('emails');
                container.innerHTML = emails.map(email => `
                    <div class="email ${email.classification?.priority || 'normal'} ${email.classification?.is_spam ? 'spam' : ''}">
                        <h3>${email.subject}</h3>
                        <p><strong>From:</strong> ${email.from}</p>
                        <p><strong>Received:</strong> ${new Date(email.received_at).toLocaleString()}</p>
                        <p>${email.snippet}</p>
                        ${email.classification ? `
                            <p><strong>Priority:</strong> ${email.classification.priority} | 
                               <strong>Action:</strong> ${email.classification.action} | 
                               <strong>Spam:</strong> ${email.classification.is_spam ? 'Yes' : 'No'}</p>
                        ` : '<p><em>Not yet classified</em></p>'}
                        <button onclick="viewEmail(${email.id})">View Details</button>
                    </div>
                `).join('');
            }
            
            async function viewEmail(emailId) {
                const response = await fetch(`/email/${emailId}`);
                const data = await response.json();
                
                const email = data.email;
                const drafts = data.drafts;
                
                const modal = document.createElement('div');
                modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000;';
                modal.innerHTML = `
                    <div style="background: white; margin: 50px; padding: 20px; border-radius: 5px; max-height: 80vh; overflow-y: auto;">
                        <h2>${email.subject}</h2>
                        <p><strong>From:</strong> ${email.from}</p>
                        <p><strong>To:</strong> ${email.to}</p>
                        <p><strong>Received:</strong> ${new Date(email.received_at).toLocaleString()}</p>
                        <hr>
                        <h3>Summary</h3>
                        <p>${data.summary?.summary || 'No summary available'}</p>
                        <hr>
                        <h3>Draft Replies</h3>
                        ${drafts.map(draft => `
                            <div class="draft">
                                <p>${draft.draft_text}</p>
                                <button class="approve-btn" onclick="approveDraft(${draft.id})">Approve & Send</button>
                            </div>
                        `).join('')}
                        <button onclick="document.body.removeChild(this.closest('div'))" style="margin-top: 20px;">Close</button>
                    </div>
                `;
                document.body.appendChild(modal);
            }
            
            async function approveDraft(draftId) {
                if (confirm('Are you sure you want to send this reply?')) {
                    const response = await fetch(`/drafts/${draftId}/approve`, { method: 'POST' });
                    if (response.ok) {
                        alert('Reply sent successfully!');
                        document.body.removeChild(document.querySelector('div[style*="position: fixed"]'));
                        loadInbox(currentFilter);
                    } else {
                        alert('Failed to send reply');
                    }
                }
            }
            
            async function pollEmails() {
                const response = await fetch('/poll', { method: 'POST' });
                const data = await response.json();
                alert(`Fetched ${data.fetched} emails, processed ${data.processed}`);
                loadInbox(currentFilter);
            }
            
            // Load initial inbox
            loadInbox();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
