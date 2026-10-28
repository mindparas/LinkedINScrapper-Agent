import re

DISQUALIFIED_INTERMEDIARY_KEYWORDS = [
    "venture", "capital", "investor", "angel", "accelerator", "incubator",
    "venture partner", "venture scout", "talent partner", "portfolio", "investment",
    "seed fund", "fund manager", "syndicate", "vc", "approach venture",
    "newsletter", "media", "buzz", "the tech buzz", "news", "digest", "podcast",
    "followers", "curator", "influencer",
    "recruiter", "talent acquisition", "staffing", "headhunter", "hr manager",
    "recruitment", "search firm", "talent advisor", "bench sales",
    "connecting ambitious", "connecting professionals", "executive search",
    "talent solutions", "career coach", "talent scout", "staffing agency",
    "recruitment consultant", "human resources", "recruitment firm", "hiring agency",
    "entrepreneurship center", "whu",
    "seeking opportunities", "open to work", "looking for new role", "aspiring"
]

GENUINE_FOUNDER_TITLES = [
    "founder", "co-founder", "cofounder", "ceo", "cto", "coo",
    "chief technology officer", "chief executive officer", "chief operating officer",
    "vp of engineering", "vp engineering", "head of engineering", "head of product"
]

STRONG_BUYING_INTENT_SIGNALS = [
    "looking for an agency", "looking for a dev shop", "need a dev shop", "need an agency",
    "software agency", "dev agency", "development partner", "software partner", "tech partner",
    "outsourcing", "outsource", "recommend an agency", "recommend a dev", "recommend developers",
    "building our mvp", "building an mvp", "build our mvp", "need help building",
    "need an mvp", "launching our mvp", "building v1", "need frontend", "need backend",
    "need developers", "need engineers", "hiring developers", "looking for developers",
    "looking for builders", "need builders", "contractors", "contract developer", "contract engineer",
    "fractional cto", "freelance engineer", "freelance developer", "seeking a developer",
    "seeking developers", "seeking engineers", "founding engineer", "first engineer",
    "lead engineer", "build our platform", "building our platform", "develop our mvp"
]

def verify_bde_lead_authenticity(author: str, headline: str, role: str = "", company: str = "", post_content: str = "") -> tuple:
    """
    Validates that a candidate is an authentic direct startup decision-maker
    and strictly eliminates:
    - VCs, investors, scouts, accelerators (e.g. Bryce Dabbs @ Approach Venture)
    - Newsletters, curators, media accounts (e.g. The Tech Buzz)
    - Recruiters, HR, headhunters, job brokers (e.g. Paul Wilkens)
    """
    author_headline = f"{author} {headline}".lower()
    full_text = f"{author} {headline} {role} {company}".lower()
    
    # 1. Check for disqualified intermediary keywords anywhere
    for kw in DISQUALIFIED_INTERMEDIARY_KEYWORDS:
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, full_text):
            return False, f"Matches intermediary/recruiter keyword: '{kw}' (Must be direct founder/CEO/CTO of their own tech startup, NOT recruiter or broker)"
            
    # 2. Check that the ACTUAL SCRAPED HEADLINE contains a direct founder/executive title
    has_founder_title = False
    for title in GENUINE_FOUNDER_TITLES:
        pattern = r'\b' + re.escape(title) + r'\b'
        if re.search(pattern, author_headline):
            has_founder_title = True
            break
            
    if not has_founder_title:
        return False, f"Actual headline '{headline}' does not indicate a direct Founder, Co-Founder, CEO, CTO, or VP of Engineering"
        
    return True, "Authentic startup decision maker"


def verify_sales_buying_intent(post_content: str, headline: str = "") -> tuple:
    """
    Validates that the post content expresses real commercial/technical buying intent
    (e.g. building an MVP, hiring developers, seeking dev shop/agency, hiring founding engineer)
    and eliminates random motivational fluff, news reposts, or unrelated company updates.
    """
    content_lower = (post_content or "").lower()
    if len(content_lower) < 25:
        return False, "Post content is too short to establish any genuine project or technical buying intent"

    # Disqualify if post itself is an overt recruiter / headhunter broadcast
    recruiter_pitch = [
        "we are an executive search", "looking to place", "candidates looking for",
        "open roles across our portfolio", "reach out if you want to be placed"
    ]
    for rp in recruiter_pitch:
        if rp in content_lower:
            return False, f"Post is a recruiter placement broadcast: '{rp}'"

    # Check for presence of strong buying or development intent signals
    matched_signals = []
    for signal in STRONG_BUYING_INTENT_SIGNALS:
        if signal in content_lower:
            matched_signals.append(signal)

    if not matched_signals:
        return False, "Post does NOT contain active buying, MVP building, or software engineering intent (general commentary/thought leadership)"

    return True, f"Active technical buying/building intent detected: {', '.join(matched_signals[:3])}"

