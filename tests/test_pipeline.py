"""
Tests for the email processing pipeline.
"""

import pytest
import json
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base, Email, Inference, Draft
from src.pipeline import process_email
from src.llm import classify_email, summarize_email, draft_reply

# Test database
TEST_DB_URL = "sqlite:///./test_email_agent.db"
engine = create_engine(TEST_DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

@pytest.fixture
def db_session():
    """Create a test database session."""
    Base.metadata.create_all(engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)

@pytest.fixture
def sample_email(db_session):
    """Create a sample email for testing."""
    email = Email(
        msg_id="test-msg-123",
        thread_id="test-thread-123",
        from_addr="test@example.com",
        to_addr="user@example.com",
        subject="Test Email Subject",
        snippet="This is a test email body with some content.",
        raw_path="/tmp/test.eml"
    )
    db_session.add(email)
    db_session.commit()
    db_session.refresh(email)
    return email

def test_classify_email_json_schema():
    """Test that classify_email returns valid JSON with expected keys."""
    with patch('src.llm.client') as mock_client:
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "priority": "normal",
            "is_spam": False,
            "action": "needs_reply",
            "reasons": ["Contains a question"]
        })
        mock_client.chat.completions.create.return_value = mock_response
        
        result = classify_email("Test Subject", "Test body with a question?")
        
        assert "priority" in result
        assert "is_spam" in result
        assert "action" in result
        assert "reasons" in result
        assert result["priority"] in ["high", "normal", "low"]
        assert isinstance(result["is_spam"], bool)
        assert result["action"] in ["archive", "needs_reply", "read_only"]

def test_summarize_email_json_schema():
    """Test that summarize_email returns valid JSON with expected keys."""
    with patch('src.llm.client') as mock_client:
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "summary": "This is a test email thread summary.",
            "participants": ["test@example.com", "user@example.com"],
            "asks": ["What is the status?"],
            "dates": ["2024-01-01T10:00:00Z"],
            "attachments": [],
            "sentiment": "neu"
        })
        mock_client.chat.completions.create.return_value = mock_response
        
        result = summarize_email("Test Subject", "Test body")
        
        assert "summary" in result
        assert "participants" in result
        assert "asks" in result
        assert "dates" in result
        assert "attachments" in result
        assert "sentiment" in result
        assert isinstance(result["participants"], list)
        assert isinstance(result["asks"], list)
        assert isinstance(result["dates"], list)
        assert isinstance(result["attachments"], list)

def test_draft_reply_json_schema():
    """Test that draft_reply returns valid JSON with expected keys."""
    with patch('src.llm.client') as mock_client:
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "options": [
                {
                    "title": "Option 1",
                    "body": "Thank you for your email. Here is my response.",
                    "assumptions": ["Standard response"]
                },
                {
                    "title": "Option 2", 
                    "body": "I appreciate you reaching out. Let me get back to you.",
                    "assumptions": ["Need more time"]
                }
            ],
            "style": "crisp"
        })
        mock_client.chat.completions.create.return_value = mock_response
        
        result = draft_reply("Test Subject", "Test body", {"summary": "Test summary"})
        
        assert "options" in result
        assert "style" in result
        assert isinstance(result["options"], list)
        assert len(result["options"]) >= 1
        for option in result["options"]:
            assert "title" in option
            assert "body" in option
            assert "assumptions" in option

@patch('src.llm.classify_email')
@patch('src.llm.summarize_email')
@patch('src.llm.draft_reply')
def test_process_email_creates_drafts_for_needs_reply(mock_draft, mock_summarize, mock_classify, db_session, sample_email):
    """Test that process_email creates drafts when action is needs_reply."""
    # Mock LLM responses
    mock_classify.return_value = {
        "priority": "normal",
        "is_spam": False,
        "action": "needs_reply",
        "reasons": ["Contains question"]
    }
    
    mock_summarize.return_value = {
        "summary": "Test summary",
        "participants": ["test@example.com"],
        "asks": ["What is the status?"],
        "dates": [],
        "attachments": [],
        "sentiment": "neu"
    }
    
    mock_draft.return_value = {
        "options": [
            {
                "title": "Option 1",
                "body": "Thank you for your email.",
                "assumptions": ["Standard response"]
            }
        ],
        "style": "crisp"
    }
    
    # Process the email
    success = process_email(db_session, sample_email)
    
    assert success is True
    
    # Check that classification was saved
    classification = db_session.query(Inference).filter(
        Inference.email_id == sample_email.id,
        Inference.kind == "classification"
    ).first()
    assert classification is not None
    assert classification.json["action"] == "needs_reply"
    
    # Check that summary was saved
    summary = db_session.query(Inference).filter(
        Inference.email_id == sample_email.id,
        Inference.kind == "summary"
    ).first()
    assert summary is not None
    
    # Check that drafts were created
    drafts = db_session.query(Draft).filter(Draft.email_id == sample_email.id).all()
    assert len(drafts) == 1
    assert drafts[0].draft_text == "Thank you for your email."

@patch('src.llm.classify_email')
def test_process_email_skips_spam(mock_classify, db_session, sample_email):
    """Test that process_email skips further processing for spam emails."""
    # Mock spam classification
    mock_classify.return_value = {
        "priority": "low",
        "is_spam": True,
        "action": "archive",
        "reasons": ["Spam indicators"]
    }
    
    # Process the email
    success = process_email(db_session, sample_email)
    
    assert success is True
    
    # Check that only classification was saved
    classification = db_session.query(Inference).filter(
        Inference.email_id == sample_email.id,
        Inference.kind == "classification"
    ).first()
    assert classification is not None
    assert classification.json["is_spam"] is True
    
    # Check that no summary or drafts were created
    summary = db_session.query(Inference).filter(
        Inference.email_id == sample_email.id,
        Inference.kind == "summary"
    ).first()
    assert summary is None
    
    drafts = db_session.query(Draft).filter(Draft.email_id == sample_email.id).all()
    assert len(drafts) == 0
