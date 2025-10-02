"""
Machine Learning-based Spam Classifier
Uses user feedback to improve spam detection over time.
"""

import logging
import re
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from .models import Email, SpamFeedback
import json

logger = logging.getLogger(__name__)

class MLSpamClassifier:
    """Simple ML-based spam classifier using heuristics and user feedback."""
    
    def __init__(self):
        # Critical spam keywords - heavily weighted
        self.money_request_keywords = [
            'donate', 'donation', 'contribute', 'contribution', 'fundraising',
            'support our mission', 'make a gift', 'give today', 'help us',
            'support us', 'join us', 'become a member', 'membership', 'renew',
            'your support matters', 'make a difference', 'support our cause',
            'sponsor', 'sponsorship', 'pledge', 'crowdfunding', 'gofundme',
            'patreon', 'kickstarter', 'campaign', 'goal', 'matching gift'
        ]
        
        self.spam_keywords = [
            'viagra', 'cialis', 'casino', 'lottery', 'winner', 'prize', 'congratulations',
            'click here', 'act now', 'limited time', 'free money', 'earn money fast',
            'work from home', 'lose weight', 'miracle', 'guarantee', 'no obligation',
            'risk free', 'call now', 'subscribe', 'unsubscribe', 'opt out',
            '100% free', 'double your', 'extra income', 'financial freedom',
            'get paid', 'increase sales', 'save big', 'special promotion',
            'deal', 'offer', 'discount', 'coupon', 'sale', 'clearance',
            'webinar', 'register now', 'sign up', 'join now', 'learn more'
        ]
        
        self.suspicious_patterns = [
            r'\$\d+[,\d]*',  # Money amounts
            r'!!!+',  # Multiple exclamation marks
            r'CLICK HERE',  # All caps calls to action
            r'BUY NOW',
            r'FREE!!!',
            r'http[s]?://bit\.ly',  # Shortened URLs
            r'http[s]?://tinyurl',
        ]
    
    def extract_features(self, email: Email, snippet: str = "") -> Dict[str, Any]:
        """Extract features from an email for classification."""
        from_addr = email.from_addr or ""
        subject = email.subject or ""
        body = snippet or email.snippet or ""
        
        # Extract domain
        domain = ""
        if "@" in from_addr:
            domain = from_addr.split("@")[-1].lower().strip(">").strip()
        
        # Count spam keywords
        text_lower = (subject + " " + body).lower()
        spam_keyword_count = sum(1 for keyword in self.spam_keywords if keyword in text_lower)
        
        # Count money request keywords (critical indicator)
        money_request_count = sum(1 for keyword in self.money_request_keywords if keyword in text_lower)
        
        # Check for suspicious patterns
        suspicious_pattern_count = sum(1 for pattern in self.suspicious_patterns if re.search(pattern, subject + " " + body, re.IGNORECASE))
        
        # Check for excessive caps
        if len(subject) > 0:
            caps_ratio = sum(1 for c in subject if c.isupper()) / len(subject)
        else:
            caps_ratio = 0
        
        # Check for links
        has_links = 'http://' in body or 'https://' in body or 'www.' in body
        
        # Check subject length (very short or very long can be spam)
        subject_length = len(subject)
        
        # Check for common marketing domains
        marketing_domains = ['marketing', 'promo', 'deals', 'offers', 'newsletter', 'noreply']
        is_marketing_domain = any(term in domain for term in marketing_domains)
        
        return {
            'from_domain': domain,
            'subject_length': subject_length,
            'body_length': len(body),
            'has_links': has_links,
            'spam_keyword_count': spam_keyword_count,
            'money_request_count': money_request_count,
            'suspicious_pattern_count': suspicious_pattern_count,
            'caps_ratio': caps_ratio,
            'is_marketing_domain': is_marketing_domain
        }
    
    def calculate_spam_score(self, features: Dict[str, Any], db: Session, user_id: int) -> float:
        """
        Calculate spam probability (0.0 to 1.0) based on features and user feedback.
        Returns: 0.0-0.3 = Not Spam, 0.3-0.7 = Potential Spam, 0.7-1.0 = Spam
        """
        score = 0.0
        
        # CRITICAL: Money requests are strong spam indicators
        money_request_count = features.get('money_request_count', 0)
        if money_request_count > 0:
            # Any money request keywords = very high spam score
            score += money_request_count * 0.35  # Each money request keyword adds 35%!
            logger.info(f"Money request detected: {money_request_count} keywords, adding {money_request_count * 0.35} to spam score")
        
        # Base heuristic scoring
        score += features['spam_keyword_count'] * 0.15  # Each keyword adds 15%
        score += features['suspicious_pattern_count'] * 0.12  # Each pattern adds 12%
        score += features['caps_ratio'] * 0.2  # Caps ratio adds up to 20%
        
        if features['is_marketing_domain']:
            score += 0.2  # Increased from 0.15
        
        if features['has_links'] and features['spam_keyword_count'] > 0:
            score += 0.15  # Increased from 0.1
        
        # Very short subjects with spam keywords
        if features['subject_length'] < 20 and features['spam_keyword_count'] > 0:
            score += 0.12
        
        # Learn from user feedback
        domain = features['from_domain']
        if domain:
            # Check if user has marked emails from this domain as spam before
            feedback = db.query(SpamFeedback).filter(
                SpamFeedback.user_id == user_id,
                SpamFeedback.from_domain == domain
            ).all()
            
            if feedback:
                spam_count = sum(1 for f in feedback if f.is_spam)
                not_spam_count = sum(1 for f in feedback if not f.is_spam)
                
                if spam_count > not_spam_count:
                    # User consistently marks this domain as spam
                    score += 0.3
                elif not_spam_count > spam_count:
                    # User consistently marks this domain as not spam
                    score -= 0.3
        
        # Cap score between 0 and 1
        return max(0.0, min(1.0, score))
    
    def classify(self, email: Email, db: Session, user_id: int, snippet: str = "", llm_classification: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Classify email as spam/potential_spam/not_spam.
        Combines ML heuristics, user feedback, and LLM classification.
        """
        features = self.extract_features(email, snippet)
        ml_score = self.calculate_spam_score(features, db, user_id)
        
        # Get LLM spam assessment if available
        llm_is_spam = False
        if llm_classification and 'is_spam' in llm_classification:
            llm_is_spam = llm_classification['is_spam']
        
        # Combine ML and LLM
        # If LLM says spam, boost the score
        if llm_is_spam:
            ml_score = min(1.0, ml_score + 0.3)
        
        # Determine classification
        if ml_score >= 0.7:
            classification = 'spam'
            confidence = 'high'
        elif ml_score >= 0.35:
            classification = 'potential_spam'
            confidence = 'medium'
        else:
            classification = 'not_spam'
            confidence = 'high' if ml_score < 0.15 else 'low'
        
        return {
            'classification': classification,
            'ml_score': ml_score,
            'confidence': confidence,
            'features': features,
            'llm_is_spam': llm_is_spam
        }
    
    def record_feedback(self, db: Session, email: Email, user_id: int, is_spam: bool, features: Dict[str, Any], llm_classification: Optional[Dict] = None):
        """Record user feedback for training."""
        try:
            feedback = SpamFeedback(
                email_id=email.id,
                user_id=user_id,
                is_spam=is_spam,
                from_domain=features.get('from_domain', ''),
                subject_length=features.get('subject_length', 0),
                body_length=features.get('body_length', 0),
                has_links=features.get('has_links', False),
                has_attachments=False,  # TODO: detect attachments
                llm_spam_score=llm_classification
            )
            db.add(feedback)
            db.commit()
            logger.info(f"Recorded spam feedback for email {email.id}: is_spam={is_spam}")
        except Exception as e:
            logger.error(f"Failed to record spam feedback: {e}")
            db.rollback()


# Global classifier instance
ml_classifier = MLSpamClassifier()

