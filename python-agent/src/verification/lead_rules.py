"""
Strict Lead Validation Rules for Autonomous LinkedIn BDE Pipeline.
Provides verified decision-maker authenticity and active commercial intent gates.
"""

from src.verification.persona_filter import verify_bde_persona, DISQUALIFIED_HEADLINE_PATTERNS as DISQUALIFIED_INTERMEDIARY_KEYWORDS, GENUINE_EXECUTIVE_TITLES as GENUINE_FOUNDER_TITLES
from src.verification.intent_engine import verify_sales_intent, STRONG_INTENT_PATTERNS as STRONG_BUYING_INTENT_SIGNALS

def verify_bde_lead_authenticity(author: str, headline: str, role: str = "", company: str = "", post_content: str = "") -> tuple:
    """
    Validates that candidate is an authentic direct startup executive decision-maker (Founder/CTO/CEO/VP)
    and strictly eliminates recruiters, brokers, intermediaries, and job seekers.
    """
    return verify_bde_persona(author=author, headline=headline, role=role, company=company)

def verify_sales_buying_intent(post_content: str, headline: str = "") -> tuple:
    """
    Validates that post content expresses authentic commercial/technical buying intent
    (MVP building, hiring developers, looking for dev shop/agency) and eliminates noise/closed roles.
    """
    return verify_sales_intent(post_content=post_content, headline=headline)
