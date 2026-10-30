"""
Commercial Buying & Technical Development Intent Engine.
Differentiates active MVP/dev/hiring needs from fluff, celebrations, and closed positions.
"""

import re
from typing import Tuple

INTENT_DISQUALIFIER_PATTERNS = [
    # ── 1. Role already filled or hiring closed ──────────────────────────────
    r'\b(?:role|position)\s+(?:is\s+)?filled\b',
    r'\bhiring\s+(?:is\s+)?closed\b',
    r'\bfilled\s+the\s+role\b',
    r'\boffer\s+accepted\b',
    r'\bno\s+longer\s+hiring\b',
    r'\bwe\s+found\s+our\s+(?:founding\s+)?engineer\b',
    r'\bwelcome\s+(?:to\s+the\s+team\b|our\s+new\b)',
    
    # ── 2. Candidate career moves / job announcements (NOT hiring) ───────────
    r'\b(?:thrilled|excited|happy|proud)\s+to\s+(?:announce|share)\s+that\s+I\s+(?:have\s+)?joined\b',
    r'\bstarted\s+a\s+new\s+position\s+as\b',
    r'\bmy\s+first\s+day\s+at\b',
    r'\bmy\s+journey\s+at\b',
    
    # ── 2b. Sellers / agencies promoting themselves (the competition, not buyers) ──
    r'\b(?:scaling|running|growing|own(?:ing)?)\s+(?:a|an|your)\s+(?:software\s+)?(?:agency|dev\s*shop|consultancy)\b',
    r'\b(?:stop|tired\s+of)\s+turning\s+down\b',
    r'\bwe\s+(?:help|build|deliver|specialize|partner\s+with)\s+(?:\w+\s+){0,3}(?:founders|startups|companies|businesses|agencies|brands)\b',
    r'\b(?:book|schedule)\s+(?:a\s+)?(?:free\s+)?(?:call|demo|consultation)\b',
    r'\b(?:dm|message)\s+me\s+(?:for|to\s+(?:get|learn))\b',
    r'\bwhite[\s-]?label\b',
    r'\b(?:our|my)\s+(?:agency|studio|dev\s*shop)\s+(?:builds|delivers|offers)\b',

    # ── 3. Generic advice / thought leadership without active requirement ───
    r'\b\d+\s+(?:lessons|tips|takeaways|things)\s+(?:I\s+learned|to\s+know|for)\b',
    r'\bwhy\s+every\s+(?:founder|startup)\s+needs\b',
    r'\bcheck\s+out\s+(?:this|my)\s+(?:article|newsletter|podcast|blog|post)\b'
]

STRONG_INTENT_PATTERNS = [
    # ── 1. Agency / Dev shop / Outsource intent ─────────────────────────────
    r'\b(?:looking|searching)\s+for\s+(?:an?\s+)?(?:agency|dev\s*shop|software\s*house|development\s*partner|tech\s*partner)\b',
    r'\bneed\s+(?:an?\s+)?(?:agency|dev\s*shop|development\s*partner|tech\s*partner)\b',
    r'\brecommend\s+(?:an?\s+)?(?:agency|dev\s*shop|developer|software\s*team)\b',
    r'\b(?:outsource|outsourcing)\s+(?:our\s+)?(?:development|dev|engineering|mvp)\b',
    
    # ── 2. MVP Building & Technical Needs ───────────────────────────────────
    r'\b(?:building|build|develop(?:ing)?|launch(?:ing)?)\s+(?:our\s+|an?\s+)?(?:mvp|v1|platform|prototype|product|app)\b',
    r'\bneed\s+help\s+(?:building|developing|shipping)\s+(?:our\s+|the\s+)?(?:mvp|v1|app|software)\b',
    r'\bseeking\s+(?:a\s+)?technical\s+co-?founder\b',
    r'\bneed\s+(?:a\s+)?technical\s+co-?founder\b',
    
    # ── 3. Active Technical Hiring / Contractor / Dev search ────────────────
    r'\b(?:hiring|looking\s+for|seeking|need)\s+(?:(?:our|a|the)\s+)?(?:first\s+)?(?:founding\s+)?(?:senior\s+|lead\s+|staff\s+)?(?:software\s+)?(?:engineer|developer|builder|cto|architect)s?\b',
    r'\b(?:hiring|looking\s+for|seeking|need)\s+(?:a\s+)?(?:full\s*stack|frontend|backend|ai|ml|mobile|react|python)\s+(?:engineer|developer|builder)s?\b',
    r'\b(?:need|looking\s+for|hiring)\s+(?:a\s+)?(?:contract|freelance|1099|fractional)\s+(?:developer|engineer|cto|lead)\b',
    r'\bwe(?:\'re|\s+are)\s+hiring\b',

    # ── 4. Looser phrasings founders actually use ───────────────────────────
    r'\b(?:anyone|anybody|someone|somebody)\s+(?:know|who\s+can|that\s+can|to)\s+(?:a\s+)?(?:good\s+)?(?:build|develop|ship|dev|developer|engineer|agency|team)',
    r'\b(?:any|can\s+(?:you|anyone))\s+(?:recommendations?|recommend|suggest)\s+(?:for\s+)?(?:a\s+)?(?:good\s+)?(?:dev|developer|engineer|agency|software|team)',
    r'\b(?:need|want|looking)\s+(?:to\s+|for\s+someone\s+to\s+)?(?:build|develop|ship)\s+(?:an?\s+|our\s+|my\s+|the\s+)?(?:\w+\s+){0,2}(?:app|mvp|product|platform|prototype|tool|saas|software)\b',
    r'\b(?:technical|tech)\s+(?:partner|co-?founder|lead)\b',
    r'\b(?:extra|more|additional)\s+(?:engineering|dev(?:eloper)?)\s+(?:capacity|hands|help|resources)\b',
    r'\b(?:hiring|recruiting)\s+(?:a\s+|our\s+first\s+)?(?:(?:senior|lead|staff|founding|first)\s+)*(?:ai|ml|full\s*stack|backend|frontend|mobile|software)\b',
    r'\bfounding\s+engineer\b',
    r'\b(?:build|building|launch(?:ing)?)\s+(?:an?\s+|our\s+|my\s+)?(?:ai|saas|startup|app)\s+(?:product|mvp|platform|startup|app)?\b[^.!?\n]{0,60}\b(?:help|need|looking|seeking|hire|hiring)\b',
    r'\bmvp\b[^.!?\n]{0,60}\b(?:help|need|looking|seeking|hire|hiring|quote|budget)\b',
    r'\b(?:help|need|looking|seeking|hire|hiring|budget)\b[^.!?\n]{0,60}\bmvp\b',
]

def verify_sales_intent(post_content: str, headline: str = "") -> Tuple[bool, str]:
    """
    Validates whether post content demonstrates active commercial buying or technical build need.
    Returns: (has_intent: bool, reason_or_signal: str)
    """
    combined = f"{post_content or ''} {headline or ''}".strip()
    if len(combined) < 25:
        return False, "Content is too short to establish genuine project or commercial buying intent"
        
    combined_lower = combined.lower()
    
    # 1. Check disqualifiers
    for pattern in INTENT_DISQUALIFIER_PATTERNS:
        m = re.search(pattern, combined_lower, re.IGNORECASE)
        if m:
            return False, f"Matches non-commercial or closed intent pattern: '{m.group(0)}'"
            
    # 2. Check strong buying intent signals
    matched = []
    for pattern in STRONG_INTENT_PATTERNS:
        m = re.search(pattern, combined_lower, re.IGNORECASE)
        if m:
            matched.append(m.group(0))
            
    if not matched:
        return False, "Post does not contain active buying, MVP building, or software engineering requirements"
        
    return True, f"High commercial intent detected: {', '.join(matched[:2])}"

