#!/usr/bin/env python3
"""
Demo script to show Email Agent functionality with sample data.
"""

import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base, Email, Inference, Draft
from src.config import settings
from src.llm import classify_email, summarize_email, draft_reply

def create_demo_data():
    """Create sample email data for demonstration."""
    
    # Setup database
    engine = create_engine(settings.DB_URL, future=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    
    # Sample emails
    sample_emails = [
        {
            "msg_id": "demo-1@example.com",
            "thread_id": "thread-1",
            "from_addr": "john@company.com",
            "to_addr": "you@example.com",
            "subject": "Meeting Request for Next Week",
            "snippet": "Hi, I hope you're doing well. I'd like to schedule a meeting to discuss the project proposal. Are you available next Tuesday at 2 PM? Please let me know if that works for you. Best regards, John",
            "raw_path": "/tmp/demo1.eml"
        },
        {
            "msg_id": "demo-2@example.com", 
            "thread_id": "thread-2",
            "from_addr": "spam@fakebank.com",
            "to_addr": "you@example.com",
            "subject": "URGENT: Verify Your Account Now!",
            "snippet": "Click here to verify your account immediately or it will be closed! Limited time offer!",
            "raw_path": "/tmp/demo2.eml"
        },
        {
            "msg_id": "demo-3@example.com",
            "thread_id": "thread-3", 
            "from_addr": "sarah@stanford.edu",
            "to_addr": "you@example.com",
            "subject": "Research Collaboration Opportunity",
            "snippet": "I'm a PhD student at Stanford and I'm interested in collaborating on your AI research project. Would you be available for a call this week to discuss potential opportunities?",
            "raw_path": "/tmp/demo3.eml"
        }
    ]
    
    print("🎯 Creating demo email data...")
    
    for email_data in sample_emails:
        # Create email record
        email = Email(**email_data)
        db.add(email)
        db.commit()
        db.refresh(email)
        
        print(f"📧 Created email: {email.subject}")
        
        # Classify email
        try:
            classification = classify_email(email.subject, email.snippet)
            print(f"   🤖 Classification: {classification['priority']} priority, {'spam' if classification['is_spam'] else 'not spam'}, action: {classification['action']}")
            
            # Save classification
            inference = Inference(
                email_id=email.id,
                kind="classification",
                json=classification,
                model="demo"
            )
            db.add(inference)
            
            # If not spam, create summary and potentially drafts
            if not classification.get("is_spam", False):
                summary = summarize_email(email.subject, email.snippet)
                print(f"   📝 Summary: {summary['summary'][:100]}...")
                
                # Save summary
                summary_inference = Inference(
                    email_id=email.id,
                    kind="summary", 
                    json=summary,
                    model="demo"
                )
                db.add(summary_inference)
                
                # Create drafts if needs reply
                if classification.get("action") == "needs_reply":
                    reply_options = draft_reply(email.subject, email.snippet, summary)
                    print(f"   ✍️  Generated {len(reply_options.get('options', []))} reply drafts")
                    
                    for i, option in enumerate(reply_options.get("options", [])):
                        draft = Draft(
                            email_id=email.id,
                            draft_text=option.get("body", ""),
                            confidence=90,
                            style=reply_options.get("style", "crisp")
                        )
                        db.add(draft)
            
            db.commit()
            
        except Exception as e:
            print(f"   ❌ Error processing email: {e}")
            db.rollback()
    
    print("\n📊 Demo data created successfully!")
    print("\nTo view the results:")
    print("1. Run 'make dev' to start the API server")
    print("2. Open http://localhost:8000 in your browser")
    print("3. You should see the demo emails with AI analysis")
    
    db.close()

if __name__ == "__main__":
    create_demo_data()
