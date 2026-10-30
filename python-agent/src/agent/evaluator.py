"""
BDE Sales Intelligence & Pitch Kit Synthesizer.
Generates tailored, high-converting outreach collateral specifically designed
for Indian offshore software & AI development agencies pitching US startup founders.
"""

import re
from typing import Dict, Any

class BDESalesIntelligenceSynthesizer:
    """
    Synthesizes rich B2B sales intelligence from qualified LinkedIn founder posts.
    Produces personalized connection notes, InMail pitches, pain point breakdowns,
    and tech stack matching.
    """

    @staticmethod
    def extract_first_name(full_name: str) -> str:
        if not full_name or full_name == "Unknown":
            return "there"
        clean = re.sub(r'^(?:Dr\.|Mr\.|Ms\.|Mrs\.|Prof\.)\s+', '', full_name.strip())
        parts = clean.split()
        return parts[0] if parts else "there"

    @staticmethod
    def detect_tech_stack(text: str) -> str:
        keywords = [
            "python", "react", "node", "typescript", "javascript", "next.js", "nextjs",
            "vue", "angular", "fastapi", "django", "flask", "ruby", "rails", "golang", "go",
            "rust", "aws", "gcp", "azure", "docker", "kubernetes", "k8s", "supabase", "postgres",
            "mongodb", "redis", "graphql", "tailwind", "flutter", "react native", "ios", "swift",
            "android", "kotlin", "pytorch", "tensorflow", "openai", "llm", "langchain", "rag",
            "vector db", "pinecone", "weaviate", "solana", "ethereum", "web3"
        ]
        text_lower = text.lower()
        found = []
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                found.append(kw.title() if kw not in ["aws", "gcp", "ai", "ml", "llm", "rag", "k8s"] else kw.upper())
        
        return ", ".join(found[:6]) if found else "Full-Stack Web & AI Architecture"

    # UI chrome / timestamp fragments the DOM scanner leaves in post text
    _NOISE_PATTERNS = [
        r'\b(?:visit|view) (?:my|our) (?:website|profile|page)\b',
        r'\b\d+\s*(?:s|m|min|h|hr|d|day|w|wk|mo|yr)s?\b(?=\s|$)',
        r'\b(?:just now|yesterday)\b',
        r'(?:…|\.\.\.)\s*(?:see\s+)?more\b',
        r'\bsee (?:more|translation)\b',
        r'\b(?:like|comment|repost|send|share|follow)\b(?=\s*(?:$|[|•]))',
        r'\bhashtag\b',
        r'#\w+',
        r'https?://\S+',
    ]

    @classmethod
    def clean_post_text(cls, text: str) -> str:
        t = (text or "")
        for pat in cls._NOISE_PATTERNS:
            t = re.sub(pat, ' ', t, flags=re.IGNORECASE)
        return re.sub(r'\s+', ' ', t).strip(" -•|·")

    @staticmethod
    def _truncate_words(s: str, limit: int) -> str:
        if len(s) <= limit:
            return s
        return s[:limit].rsplit(' ', 1)[0].rstrip(',;:-') + "…"

    @classmethod
    def extract_pain_point_summary(cls, content: str, headline: str) -> str:
        text = cls.clean_post_text(content)
        if not text:
            return "Active engineering and product development requirements."
            
        sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if len(s.strip()) > 15]
        
        # Strongest need signals first so generic words ("building") don't win over "hiring ... MVP"
        tiers = [
            ["dev shop", "agency", "outsourc", "mvp", "v1", "hiring", "looking for", "seeking"],
            ["need", "building", "build"],
        ]
        for triggers in tiers:
            for s in sentences:
                s_low = s.lower()
                if any(k in s_low for k in triggers):
                    return cls._truncate_words(s, 120)

        return cls._truncate_words(sentences[0], 120) if sentences else "Accelerating software MVP engineering and founder-led product roadmap."

    @staticmethod
    def categorize_intent(content: str) -> str:
        c_low = (content or "").lower()
        if "dev shop" in c_low or "agency" in c_low or "outsource" in c_low:
            return "Dev Shop / Software Agency Search"
        elif "mvp" in c_low or "v1" in c_low or "prototype" in c_low:
            return "MVP / Early-Stage Product Build"
        elif "founding engineer" in c_low or "first engineer" in c_low:
            return "Hiring Founding Dev (Agency Augmentation Opportunity)"
        elif "contract" in c_low or "fractional" in c_low or "freelance" in c_low:
            return "Contractor / Fractional Technical Support"
        elif "ai" in c_low or "llm" in c_low or "rag" in c_low or "model" in c_low:
            return "AI / Machine Learning Engineering Integration"
        return "Core Technical Build & Engineering Acceleration"

    @classmethod
    def synthesize_pitch_kit(
        cls,
        author: str,
        headline: str,
        company: str,
        location: str,
        post_content: str,
        niche: str = "custom software & AI MVP engineering"
    ) -> Dict[str, Any]:
        first_name = cls.extract_first_name(author)
        tech_stack = cls.detect_tech_stack(post_content)
        pain_point = cls.extract_pain_point_summary(post_content, headline)
        intent_cat = cls.categorize_intent(post_content)
        comp_display = company if company and company.lower() != "startup" else "your startup"

        # ── 1. Personalized Connection Request Note (< 300 characters) ─────────
        topic = cls._truncate_words(pain_point.rstrip("…. "), 70)
        note = (
            f"Hi {first_name}, your post on \"{topic}\" caught my eye. "
            f"We help US tech founders ship production-grade MVPs in weeks without US salary burn. "
            f"Would love to connect!"
        )
        if len(note) > 295:
            note = (
                f"Hi {first_name}, saw your post on building {comp_display}. "
                f"We specialize in rapid {niche} for US seed startups. "
                f"Would love to connect and share how we help accelerate dev timelines!"
            )
        connection_note = note[:299].strip()

        # ── 2. Full InMail / Cold Pitch Message ────────────────────────────────
        inmail_pitch = (
            f"Hi {first_name},\n\n"
            f"I came across your recent LinkedIn update regarding \"{pain_point.rstrip('…. ')}\". "
            f"Navigating technical hiring while trying to ship v1 at high velocity is often one of the biggest bottlenecks for US tech founders.\n\n"
            f"Our specialized engineering squad partners with early-stage US founders to provide battle-tested, senior developers ({tech_stack}). "
            f"We've helped 35+ venture-backed startups ship production-ready MVPs in under 6 weeks—delivering high-velocity sprint cadence without the $180k/yr US burn rate.\n\n"
            f"Would you be open to a brief 10-minute chat this Thursday to explore if our team could help accelerate your roadmap?\n\n"
            f"Best regards,\nBDE Team"
        )

        return {
            "first_name": first_name,
            "tech_stack": tech_stack,
            "pain_point": pain_point,
            "intent_category": intent_cat,
            "connection_note": connection_note,
            "inmail_pitch": inmail_pitch
        }

