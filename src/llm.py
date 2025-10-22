import openai
import json
import logging
from typing import Dict, Any
from .config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPTS = {
    "classifier": """You are an ULTRA-AGGRESSIVE email triage classifier. Your PRIMARY goal is protecting the user's attention from ANY unsolicited content. Output strict JSON:
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

PROMOTIONAL & SALES CONTENT (AUTO-SPAM):
- ALL marketing emails, newsletters, promotions, sales pitches
- "Unsubscribe" or "opt-out" links = automatic spam
- Mass emails from marketing platforms (SendGrid, Mailchimp, Constant Contact)
- ANYTHING offering a promotion, special, sale, discount, deal, or coupon
- "Save 20%", "50% off", "Buy now", "Limited time", "Flash sale", "Clearance"
- "Special offer", "Exclusive deal", "Today only", "Don't miss", "Last chance"
- "Black Friday", "Cyber Monday", "Holiday sale", "End of season"
- Product announcements you didn't request
- "New arrivals", "Just launched", "Now available"
- "Act now", "Don't miss out", "Hurry", "Expires soon"
- Generic greetings: "Dear Customer", "Hello Friend", "Hi there", "Valued customer"
- Event invitations from organizations (not personal invites from colleagues)
- Webinar invitations, conference promotions
- Survey requests from companies
- Newsletter signups you don't remember
- Retail/e-commerce marketing ("Shop now", "Browse collection", "See what's new")

RETAIL PROMOTIONAL EMAILS (ULTRA-AGGRESSIVE FILTERING):
- ANY email from Amazon that is NOT an order confirmation, shipping update, or return/refund
- Amazon Business offers, Prime Video content updates, Prime Day announcements
- Walmart/Target/BestBuy/Home Depot promotional emails
- "Recommended for you", "You might like", "Based on your interests"
- "Deals of the day", "Daily deals", "Deal of the week"
- Product recommendations unless you explicitly requested them
- "People also bought", "Customers who bought X also bought Y"
- Wishlist/cart reminders with promotional angles
- "Items on sale from your wishlist"
- "Your favorites are on sale"
- Subscription renewal reminders with promotional content (50%+ marketing)
- Emails from no-reply@, noreply@, marketing@, deals@, offers@, promotions@
- ANY retail email that says "Shop", "Browse", "Explore", "Discover", "Check out"
- Price drop notifications for items you didn't explicitly watch
- "Back in stock" notifications you didn't subscribe to
- Gift guides, seasonal shopping guides, holiday gift ideas
- "Shop our [category]" emails from any retailer
- Member-exclusive offers from retail loyalty programs (unless it's a pure points balance update)

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
- Shipping notifications for YOUR orders (ONLY tracking/delivery updates)
- Appointment confirmations YOU scheduled
- School/university official communications if you're a student/parent
- Pure account security alerts (password changed, new login, etc.) with NO promotional content
- Return/refund confirmations from retailers
- Order cancellation confirmations

IMPORTANT: Even if an email is from Amazon/Walmart/Target and contains your name:
- If it says "Shop", "Browse", "Deals", "Sale", "Recommended" → SPAM
- If it's 50%+ promotional content → SPAM
- If it's ONLY "Order #12345 has shipped" → NOT SPAM

PRIORITY LEVELS:
- high: urgent deadlines from real people, financial obligations, time-sensitive work, scheduling/appointments/meeting invites, time-sensitive requests (e.g., today/ASAP/by EOD)
- normal: standard work/personal correspondence, routine transactions
- low: receipts, notifications, FYI messages

ACTION TYPES:
- needs_reply: ONLY if a real person asks you a direct question or needs your response
- read_only: informational, receipts, notifications (no response needed)
- archive: spam, resolved issues, old threads

THREADS AND REPLIES:
- Treat emails sharing the same thread_id as part of the same thread; consider thread context if provided
- If an email is part of a thread and the user has already replied (replied_at set), DO NOT mark as needs_reply
- Prefer high priority for meeting invites, calendar events, RSVPs, and scheduling messages

⚠️ CRITICAL RULES:
1. If it asks for money → spam (unless it's a bill/invoice for services you use)
2. If it has "unsubscribe" → spam (with rare exceptions for important subscriptions)
3. If it's from a marketing platform → spam
4. Generic greeting → likely spam
5. If you can't tell if it's personal → mark as potential spam (spam_confidence 0.5)
6. When in doubt, mark as spam or potential spam - protect the user's time!
7. ANY mention of promotion/special/sale/discount/deal → IMMEDIATE SPAM
8. ANY retail/e-commerce marketing → IMMEDIATE SPAM
9. Fundraising/donations → IMMEDIATE SPAM
10. "Limited time", "Act now", "Don't miss" → IMMEDIATE SPAM
11. From no-reply@, noreply@, marketing@, deals@, offers@ → IMMEDIATE SPAM
12. "Shop", "Browse", "Explore", "Discover" from retailers → IMMEDIATE SPAM
13. "Recommended for you", "You might like", "Based on your" → IMMEDIATE SPAM
14. Amazon/Walmart/Target emails with ANY promotional content → IMMEDIATE SPAM
15. Product recommendations from any retailer → IMMEDIATE SPAM

Be ULTRA-AGGRESSIVE. It's better to over-filter than let ANY promotional/sales content through. Err on the side of marking as spam.""",

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


# Agent prompts
SYSTEM_PROMPTS.update({
    "agent_router": """You are AgentMail Orchestrator. Decide which tools to invoke to produce a daily email digest.
Think like a power user: minimize latency, prioritize important emails, and avoid unnecessary work.
Return JSON: {rationale, tasks:[{name, inputs}]}.
Allowed tasks (compose a sequence):
- collect_today_stats {include_breakdown?: bool}
- rank_emails {limit?: number, prefer: ["needs_reply","high"], exclude_spam: true}
- select_top_emails {limit: number, from: "ranked"|"all", filters: {exclude_spam:true, actions?:[...], priorities?:[...]}}
- ensure_summaries {limit?: number, source: "top"}
- draft_daily_summary {}
Guidelines:
- Always start with collect_today_stats
- If many emails, call rank_emails before select_top_emails
- Prefer needs_reply and high priority
- Keep summaries to top items only to save time
- End with draft_daily_summary""",
    "daily_summarizer": """Create a concise summary of emails.
Input:{stats:{count}, top_items:[{subject, from, received_at, importance, summary}], section: "recent_24h" OR "needs_reply"}
Output JSON:{overview: "1-2 sentence summary"}
For recent_24h: Summarize what happened in the last day.
For needs_reply: Emphasize urgency and importance of replies needed.
Keep it brief and actionable."""
})

def agent_route(state: Dict[str, Any]) -> Dict[str, Any]:
    return call_llm("agent_router", state, model_override="gpt-4o-mini")

def daily_digest_summarize(payload: Dict[str, Any]) -> Dict[str, Any]:
    return call_llm("daily_summarizer", payload, model_override="gpt-4o-mini")

# Email ranking prompt and helper
SYSTEM_PROMPTS.update({
    "email_ranker": """Rank emails by importance for today's digest.
Input: {items:[{id, subject, from, received_at, importance, action, summary?}]}
Output JSON: {ordered_ids:[...]} with most important first.
Preference: needs_reply > high priority > recent > has summary."""
})

def rank_emails(payload: Dict[str, Any]) -> Dict[str, Any]:
    return call_llm("email_ranker", payload, model_override="gpt-4o-mini")
