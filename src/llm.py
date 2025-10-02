import openai
import json
import logging
from typing import Dict, Any
from .config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPTS = {
    "classifier": """You are an email triage classifier. Output strict JSON with keys:
{"priority": "high|normal|low", "is_spam": true|false, "action": "archive|needs_reply|read_only", "reasons": ["..."]}

Criteria:
- high: deadlines, executives, money, customer/partner escalation, interview loop, invoices due <7d.
- spam: promos, tracking pixels, suspicious links; but not transactional receipts.
- needs_reply: explicit question, blocked party, scheduling request, open thread.

Only use content provided. Be conservative.""",

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
