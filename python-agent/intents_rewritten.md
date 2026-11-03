# Intents (rewritten for the agent)

Format: one block per intent. `Intent:` is the exact text passed to `--intent`; `Niche:` is passed to `--niche`.
Rules followed: US stated explicitly, author type stated, short search phrases (2-6 words), explicit exclusions,
no "likes" limits (the agent cannot read reaction counts), one need per intent.
Run all with: `.venv/bin/python run_intents.py` (see that file for options).

## Intent 1: On-demand / flexible engineering partner
Niche: custom software engineering and AI development
Intent: US-based founders, CTOs or heads of engineering who want a flexible, on-demand engineering partner that can scale up and down with a variable workload, explicitly not a full retainer or full outsourcing. Typical phrases: on-demand dev partner, flexible engineering partner, overflow capacity, plug into our team, variable workload. Any founder or tech leader at a non-agency company counts. Exclude agencies, freelancers and recruiters advertising their own services, and job seekers.

## Intent 2: Agency / dev firm recommendation request
Niche: custom software engineering and AI development
Intent: US-based founders, executives or tech leaders who ask their network to recommend or introduce them to a software development agency or dev partner. Typical phrases: can anyone recommend a dev agency, looking for a development partner, would appreciate an intro, recommend a software firm, app development company recommendations. Exclude agencies, freelancers and recruiters replying or advertising their own services.

## Intent 3: Staff augmentation / contract developers
Niche: custom software engineering and AI development
Intent: US-based founders, engineering managers, CTOs or hiring managers who need contract or augmented developers for a defined period, not a permanent hire. Typical phrases: contract engineers, short-term engineering help, augment our team, dedicated developers, offshore team, need senior React developers for 3 months. Roles can be iOS, Android, Flutter, React Native, backend, frontend, full stack, DevOps or QA. Any author type with hiring authority is fine. Exclude recruiters, staffing firms, job seekers and freelancers offering their availability.

## Intent 4: MVP / new product build (founder led)
Niche: custom software engineering and AI development
Intent: US-based non-technical or early-stage founders who are looking for a team to build their first version (MVP) of a product, instead of hiring a technical co-founder. Typical phrases: looking for a team to build our MVP, need a technical partner, build our app from scratch, product development partner, just raised need engineering. Exclude agencies and freelancers advertising their own services, and people seeking an equity co-founder only.

## Intent 5: Product rescue / takeover / modernization
Niche: custom software engineering and AI development
Intent: US-based founders, CTOs or business owners who are unhappy with their current software vendor or stuck with legacy technology and are asking for help. Typical phrases: our previous agency, need help stabilizing our app, taking over an existing codebase, migrating from legacy, rebuilding our platform, cloud migration partner. The author must state their own need; exclude thought-leadership posts about tech debt, ordinary app users complaining, and agencies advertising their services.

## Intent 6: Specialized capability gap (AI, healthcare, IoT)
Niche: AI, healthcare and IoT software engineering
Intent: US-based founders, CTOs or product leaders at non-agency companies who lack a niche skill and are looking for an outside partner for it: LLM integration, AI agent or RAG/GenAI development, HIPAA-compliant app development, FHIR/EHR integration, remote patient monitoring, IoT dashboards or digital twins. Typical phrases: need help integrating LLMs, AI agent development partner, HIPAA compliant app, FHIR integration, IoT platform partner. Exclude agencies and consultants advertising these services, and job postings for full-time employees.
