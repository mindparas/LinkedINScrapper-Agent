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

    @staticmethod
    def extract_pain_point_summary(content: str, headline: str) -> str:
        text = (content or "").strip()
        if not text:
            return "Active engineering and product development requirements."
            
        sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if len(s.strip()) > 15]
        
        # Look for the sentence containing hiring or building triggers
        for s in sentences:
            s_low = s.lower()
            if any(k in s_low for k in ["hiring", "looking for", "need", "building", "seeking", "mvp", "v1"]):
                return s[:120].strip() + ("..." if len(s) > 120 else "")
                
        return sentences[0][:120].strip() if sentences else "Accelerating software MVP engineering and founder-led product roadmap."

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
        comp_display = company or "your startup"

        # ── 1. Personalized Connection Request Note (< 300 characters) ─────────
        note = (
            f"Hi {first_name}, saw your note on {pain_point[:60]}... "
            f"We help US tech founders ship production-grade MVPs in weeks without US salary burn. "
            f"Would love to connect and follow your build!"
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
            f"I came across your recent LinkedIn update regarding {pain_point}. "
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

