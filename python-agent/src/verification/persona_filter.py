"""
Strict Persona & Startup Decision-Maker Verification Engine.
Eliminates recruiters, staffing brokers, VCs, job seekers, and non-executive profiles.
"""

import re
from typing import Tuple

DISQUALIFIED_HEADLINE_PATTERNS = [
    # ── 1. Recruiters, HR, Headhunters, Staffing ─────────────────────────────
    r'\brecruit(?:er|ing|ment)\b',
    r'\btalent acquisition\b',
    r'\bheadhunter\b',
    r'\bhr manager\b',
    r'\bhuman resources\b',
    r'\bsearch firm\b',
    r'\bexecutive search\b',
    r'\bstaffing\b',
    r'\btalent partner\b',
    r'\btalent scout\b',
    r'\btalent advisor\b',
    r'\btalent solutions\b',
    r'\bcareer coach\b',
    r'\bhiring agency\b',
    r'\bbench sales\b',
    r'\bplacement specialist\b',
    r'\brecruitment consultant\b',
    
    # ── 2. Intermediary Staffing Brokers Disguised as Founders ──────────────
    r'\bhiring (?:founding )?engineers? for (?:ai )?startups\b',
    r'\bhiring (?:developers?|engineers?|talent) for (?:clients?|companies|startups)\b',
    r'\bconnecting (?:ambitious )?professionals\b',
    r'\bconnecting talent\b',
    r'\bplacing talent\b',
    r'\bhelp(?:ing)? (?:startups|companies|founders) hire\b',
    r'\btalent brokerage\b',
    
    # ── 3. Pure Investors / VCs / Accelerators / Media Curators ──────────────
    r'\bventure partner\b',
    r'\bventure scout\b',
    r'\bmanaging director @ (?:ventures?|capital|fund)\b',
    r'\bgeneral partner @\b',
    r'\binvestor @\b',
    r'\bangel investor\b',
    r'\bventure capital\b',
    r'\bseed fund\b',
    r'\bfund manager\b',
    r'\bnewsletter\b',
    r'\bcurator\b',
    r'\bpodcast host\b',
    r'\bmedia company\b',
    
    # ── 4. Students, Interns, Job Seekers ────────────────────────────────────
    r'\bintern\b',
    r'\binternship\b',
    r'\bstudent\b',
    r'\bseeking (?:new )?(?:opportunities|roles?|jobs?)\b',
    r'\bopen to work\b',
    r'\blooking for (?:a )?(?:new )?(?:role|job|opportunity)\b',
    r'\baspiring\b'
]

GENUINE_EXECUTIVE_TITLES = [
    r'\bfounder\b',
    r'\bco-founder\b',
    r'\bcofounder\b',
    r'\bceo\b',
    r'\bcto\b',
    r'\bchief executive officer\b',
    r'\bchief technology officer\b',
    r'\bchief operating officer\b',
    r'\bvp of engineering\b',
    r'\bvp engineering\b',
    r'\bhead of engineering\b',
    r'\bhead of product\b',
    r'\bfractional cto\b',
    r'\btechnical advisor\b',
    r'\bmanaging director\b',
    r'\bowner\b',
    r'\bpresident\b',
    r'\bchief\b',
    r'\bvice president\b',
    r'\bvp\b',
    r'\bhead of (?:technology|engineering|product|ai|data)\b',
    r'\bdirector of (?:engineering|technology|product)\b',
    r'\bfounding (?:team|member|partner)\b',
    r'\bentrepreneur\b',
    r'\bbuilder (?:@|at\b)',
    r'\bbuilding (?:@|at\b)',
]

def verify_bde_persona(author: str, headline: str, role: str = "", company: str = "") -> Tuple[bool, str]:
    """
    Validates whether candidate is an authentic direct startup executive decision-maker.
    Returns: (is_authentic: bool, reason: str)
    """
    target = f"{author} {headline} {role}".lower()
    
    # 1. Check disqualifications
    for pattern in DISQUALIFIED_HEADLINE_PATTERNS:
        m = re.search(pattern, target, re.IGNORECASE)
        if m:
            return False, f"Matches disqualified persona pattern: '{m.group(0)}' (Must be direct founder/CEO/CTO of their own tech startup, NOT recruiter or broker)"
            
    # 2. Check direct decision maker title
    has_title = False
    for title in GENUINE_EXECUTIVE_TITLES:
        if re.search(title, target, re.IGNORECASE):
            has_title = True
            break
            
    if not has_title:
        return False, f"Actual headline '{headline}' does not indicate an authentic tech decision maker (Founder/CTO/VP/CEO)"
        
    return True, "Authentic startup decision maker"

