import openai
import json
import logging
from typing import Dict, Any
from .config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPTS = {
    "classifier": """You are an extremely aggressive email triage classifier. Your PRIMARY goal is protecting the user's attention from ANY unsolicited content. Output strict JSON:
{"priority": "high|normal|low", "is_spam": true|false, "spam_confidence": 0.0-1.0, "action": "archive|needs_reply|read_only", "reasons": ["..."]}

🚨 MARK AS SPAM (is_spam=true, spam_confidence >= 0.7):

MONEY REQUESTS (critical - these are spam):
- ANY donation requests (charities, nonprofits, political campaigns, causes)
- Fundraising emails ("support our mission", "make a gift", "donate today")
- Membership renewals for organizations you didn't explicitly join
- Subscription requests ("become a member", "join us", "support us")
- Crowdfunding campaigns
- "Help us reach our goal"
- ANY email asking for money that isn't a bill/invoice you owe
- Sponsorship requests
- "Your contribution matters"
- Appeals for financial support

MARKETING & PROMOTIONS:
- ALL marketing emails, newsletters, promotions, sales pitches
- "Unsubscribe" or "opt-out" links = automatic spam
- Mass emails from marketing platforms (SendGrid, Mailchimp, Constant Contact)
- Sales offers, deals, discounts, coupons, special offers
- Product announcements you didn't request
- "Limited time offer", "Act now", "Don't miss out"
- Generic greetings: "Dear Customer", "Hello Friend", "Hi there"
- Event invitations from organizations (not personal invites from colleagues)
- Webinar invitations, conference promotions
- Survey requests from companies
- Newsletter signups you don't remember

SUSPICIOUS CONTENT:
- Shortened URLs (bit.ly, tinyurl, goo.gl)
- Cryptocurrency, forex, trading, investment schemes
- Get-rich-quick, work-from-home schemes
- Weight loss, pharmacy, supplements, CBD, medical offers
- Adult content, dating sites
- Lottery, prizes, "You've won", inheritance scams
- "Verify your account" from unknown senders
- Password resets you DIDN'T initiate
- Requests for personal/financial information
- "Update your payment method" from non-merchants

🟠 POTENTIAL SPAM (is_spam=false, spam_confidence 0.35-0.7):

BORDERLINE CASES:
- Newsletters you DID subscribe to but are promotional
- Receipts with heavy marketing (50%+ is marketing content)
- Automated notifications with promotional content
- "Updates" that are really sales pitches
- Career/job newsletters (unless from recruiter reaching out directly)
- Educational content with sales angles
- Company updates that include promotions
- Event reminders with sponsorship messages

✅ NOT SPAM (is_spam=false, spam_confidence < 0.35):

LEGITIMATE EMAILS ONLY:
- Direct personal emails from real people (not form emails)
- Work emails from colleagues, managers, direct reports
- Transactional receipts ONLY (pure order confirmations, no marketing)
- Bills/invoices you actually owe from services you use
- Password resets/2FA codes YOU initiated in the last hour
- Calendar invites from known colleagues (not event marketing)
- Banking/financial statements from YOUR bank
- Government, tax, legal correspondence addressed to you
- Customer support responses to YOUR tickets
- Shipping notifications for YOUR orders
- Appointment confirmations YOU scheduled
- School/university official communications if you're a student/parent

PRIORITY LEVELS:
- high: urgent deadlines from real people, financial obligations, time-sensitive work
- normal: standard work/personal correspondence, routine transactions
- low: receipts, notifications, FYI messages

ACTION TYPES:
- needs_reply: ONLY if a real person asks you a direct question or needs your response
- read_only: informational, receipts, notifications (no response needed)
- archive: spam, resolved issues, old threads

⚠️ CRITICAL RULES:
1. If it asks for money → spam (unless it's a bill/invoice for services you use)
2. If it has "unsubscribe" → spam (with rare exceptions for important subscriptions)
3. If it's from a marketing platform → spam
4. Generic greeting → likely spam
5. If you can't tell if it's personal → mark as potential spam (spam_confidence 0.5)
6. When in doubt, mark as spam or potential spam - protect the user's time!

Be EXTREMELY aggressive. It's better to over-filter than let promotional content through.""",

    "summarizer": """Summarize the entire thread in <= 3 sentences.
Also extract: {participants: [name@email], asks: ["..."], dates: [ISO], attachments: ["name.ext"], sentiment: "pos|neu|neg"}.
Return JSON: {summary, participants, asks, dates, attachments, sentiment}.""",

    "reply": """Draft 2 concise replies that directly address the sender's asks.
Tone: friendly, crisp, professional; American English; no fluff; keep to <150 words.
Respect any proposed times; if scheduling, suggest 2 concrete slots in PT.
End with the provided signature if present.
Return JSON: {options: [{title, body, assumptions}], style: "crisp"}.""",

    "style_guard": """Rewrite the reply to be clear, specific, and polite. Keep facts, shorten filler, remove hedging."""
}

def call_llm(kind: str, content: Dict[str, Any], model_override: str = None) -> Dict[str, Any]:
    """Call the LLM with the specified prompt type and content."""
    if kind not in SYSTEM_PROMPTS:
        raise ValueError(f"Unknown prompt kind: {kind}")
    
    system_prompt = SYSTEM_PROMPTS[kind]
    
    # Use GPT-4o-mini for classifier and summarizer, GPT-5 for reply drafts
    if model_override:
        model = model_override
    elif kind in ["classifier", "summarizer"]:
        model = "gpt-4o-mini"
        logger.info(f"Using gpt-4o-mini for {kind}")
    else:
        model = settings.MODEL_NAME  # GPT-5 for drafts
        logger.info(f"Using {model} for {kind}")
    
    # Convert content dict to string for the user message
    user_content = json.dumps(content, indent=2)
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"}
            # Using default temperature (1) - both models don't support custom temperature values
        )
        
        result = json.loads(response.choices[0].message.content)
        logger.info(f"LLM call successful for {kind} using {model}")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"LLM call failed for {kind}: {e}")
        raise

def classify_email(subject: str, body: str, headers: Dict[str, str] = None) -> Dict[str, Any]:
    """Classify an email for priority, spam, and action needed."""
    content = {
        "subject": subject,
        "body": body,
        "headers": headers or {}
    }
    return call_llm("classifier", content)

def summarize_email(subject: str, body: str, thread_context: str = "") -> Dict[str, Any]:
    """Summarize an email thread."""
    content = {
        "subject": subject,
        "body": body,
        "thread_context": thread_context
    }
    return call_llm("summarizer", content)

def draft_reply(subject: str, body: str, summary: Dict[str, Any], signature: str = "") -> Dict[str, Any]:
    """Draft reply options for an email."""
    content = {
        "subject": subject,
        "body": body,
        "summary": summary,
        "signature": signature
    }
    return call_llm("reply", content)

def improve_style(text: str) -> str:
    """Improve the style of a reply draft."""
    content = {"text": text}
    result = call_llm("style_guard", content)
    return result.get("improved_text", text)
