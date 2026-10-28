import re

DISQUALIFIED_INTERMEDIARY_KEYWORDS = [
    "venture", "capital", "investor", "angel", "accelerator", "incubator",
    "venture partner", "venture scout", "talent partner", "portfolio", "investment",
    "seed fund", "fund manager", "syndicate", "vc", "approach venture",
    "newsletter", "media", "buzz", "the tech buzz", "news", "digest", "podcast",
    "followers", "curator", "influencer",
    "recruiter", "talent acquisition", "staffing", "headhunter", "hr manager",
    "recruitment", "search firm", "talent advisor", "bench sales",
    "entrepreneurship center", "whu",
    "seeking opportunities", "open to work", "looking for new role", "aspiring"
]

GENUINE_FOUNDER_TITLES = [
    "founder", "co-founder", "cofounder", "ceo", "cto",
    "chief technology officer", "chief executive officer",
    "vp of engineering", "vp engineering", "head of engineering", "head of product"
]

def verify_bde_lead_authenticity(author: str, headline: str, role: str = "", company: str = "") -> tuple:
    """
    Validates that a candidate is an authentic direct startup decision-maker
    (like Billy Jeremijenko, Founder of Symbolia) and strictly eliminates:
    - VCs, investors, scouts, accelerators (e.g. Bryce Dabbs @ Approach Venture)
    - Newsletters, curators, media accounts (e.g. The Tech Buzz)
    - Recruiters, HR, job seekers, and talent brokers
    """
    author_headline = f"{author} {headline}".lower()
    full_text = f"{author} {headline} {role} {company}".lower()
    
    # 1. Check for disqualified intermediary keywords anywhere
    for kw in DISQUALIFIED_INTERMEDIARY_KEYWORDS:
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, full_text):
            return False, f"Matches intermediary/non-client keyword: '{kw}' (Must be direct founder/CEO/CTO of their own startup, not VC/scout/media)"
            
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

