"""
OpenAI Function Calling Tool Specifications for LinkedIn BDE Autonomous Agent.
Defines schemas for all 10 tools available to the agent.
"""

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_search",
            "description": "Execute a LinkedIn content search using high-intent founder keywords anchored to US Tech Hubs (e.g. 'San Francisco', 'Austin', 'NYC') or US Accelerators ('YC', 'Techstars').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "High-intent search query. MUST incorporate at least one US Lead Magnet: 1) US Tech Hub (e.g. '\"San Francisco\" \"founding engineer\"', '\"Austin\" \"founding engineer\"', '\"NYC\" \"first engineer\"'), 2) US Accelerators (e.g. 'YC \"founding engineer\" hiring', '\"Techstars\" \"founding engineer\"'), or 3) US Hiring constraints ('\"US only\" \"founding engineer\"'). Use double quotes around exact multi-word cities or compound titles. NEVER put generic 'United States' or 'USA' in the query box as that yields 0 founder posts."
                    },
                    "freshness": {
                        "type": "string",
                        "enum": ["past-24h", "past-week"],
                        "description": "Freshness window ('past-24h' or 'past-week'). Favor 'past-week' when running during non-US business hours to capture active US founder posts from the week."
                    },
                    "target_objective": {
                        "type": "string",
                        "description": "What specific goal, prospective client persona, or lead profile do you want to achieve with this search? (e.g. Early-stage AI/SaaS founders seeking technical MVP development partners)."
                    },
                    "query_rationale": {
                        "type": "string",
                        "description": "Strategic reason why this specific unquoted query phrasing was chosen."
                    },
                    "feasibility_analysis": {
                        "type": "string",
                        "description": "Will you be able to achieve the objective with this query, what posts will it attract, and why will it avoid noise and recruiters?"
                    },
                    "developer_feedback_alignment": {
                        "type": "string",
                        "description": "Explicitly how this query strictly obeys and incorporates all developer guidance provided."
                    }
                },
                "required": [
                    "query",
                    "freshness",
                    "target_objective",
                    "query_rationale",
                    "feasibility_analysis",
                    "developer_feedback_alignment"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_and_read_cards",
            "description": "Extract and read un-evaluated post cards visible in the DOM to examine the author, headline, profile link, and post content.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_profile_location",
            "description": "Opens the author's LinkedIn profile in a background tab to check and confirm their exact verified location string (e.g. San Francisco, CA, USA vs Bangalore, India).",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_index": {"type": "integer", "description": "Card index on screen"},
                    "author_url": {"type": "string", "description": "Author's profile URL (https://www.linkedin.com/in/...)"}
                },
                "required": ["card_index", "author_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_feed",
            "description": "Scroll down the LinkedIn feed to load more candidate posts for the current query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "integer",
                        "description": "Number of scroll steps (default: 1)"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why scrolling is needed"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "qualify_and_save_lead",
            "description": "Qualifies an authentic US decision-maker lead, captures its exact post shortlink URL, and saves to CSV (Profile URL, Post URL, Fit Score) and JSON.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_index": {"type": "integer", "description": "Card index on screen"},
                    "author": {"type": "string", "description": "Author name"},
                    "profile_url": {"type": "string", "description": "Author's LinkedIn profile URL (https://www.linkedin.com/in/...)"},
                    "headline": {"type": "string", "description": "Author headline/title"},
                    "role": {"type": "string", "description": "Role (e.g. Founder, CEO, CTO, VP Engineering)"},
                    "company": {"type": "string", "description": "Company name"},
                    "location": {"type": "string", "description": "Verified US location (e.g. San Francisco, CA / Austin, TX)"},
                    "fit_score": {"type": "integer", "description": "BDE Fit score 0-100"},
                    "custom_pitch": {"type": "string", "description": "1-2 sentence customized cold outreach hook mentioning their specific project"},
                    "buying_intent_signal": {"type": "string", "description": "The specific commercial or technical buying intent extracted from the post (e.g. building an MVP, looking for dev shop, hiring founding engineer)"},
                    "reasoning": {"type": "string", "description": "Why this lead is qualified"}
                },
                "required": ["card_index", "author", "profile_url", "headline", "role", "company", "location", "fit_score", "custom_pitch", "reasoning"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skip_card",
            "description": "Disqualify an unqualified post card with an explicit rejection reason (e.g. Recruiter, Non-US location leak, Stale post, Job seeker).",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_index": {"type": "integer", "description": "Card index on screen"},
                    "author": {"type": "string", "description": "Author name"},
                    "rejection_reason": {"type": "string", "description": "Specific reason for skipping"}
                },
                "required": ["card_index", "author", "rejection_reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web to investigate company HQ, verify an author's background, or look up trending BDE queries for US startups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Web search keywords (e.g. 'Symbolia AI company headquarters')"},
                    "rationale": {"type": "string", "description": "Why this web search is needed"}
                },
                "required": ["query", "rationale"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_code_improvement",
            "description": "Propose a self-improvement code modification to tools, DOM extractors, query parsers, or filters when an issue is diagnosed. Must include detailed explanation, expected benefit, target code snippet, and replacement snippet with try-except blocks. Requests user confirmation in the terminal and verifies syntax before applying.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Target file to update (e.g. 'linkedin_bde_intelligent_pipeline.py')"
                    },
                    "target_code": {
                        "type": "string",
                        "description": "Exact code snippet in the file to replace"
                    },
                    "replacement_code": {
                        "type": "string",
                        "description": "Improved replacement code snippet including robust try-except handling"
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Detailed explanation of what issue was detected and what this code modification changes"
                    },
                    "expected_benefit": {
                        "type": "string",
                        "description": "How this change will improve query processing, location detection, or scraping accuracy"
                    }
                },
                "required": ["file_path", "target_code", "replacement_code", "explanation", "expected_benefit"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_developer",
            "description": "Ask the human developer for advice, clarification, query suggestions, or decision guidance whenever you hit an edge case, encounter ambiguous profiles, or want a recommendation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Specific question or decision point you need developer input on"
                    },
                    "context": {
                        "type": "string",
                        "description": "Relevant context (current query, candidate name, or situation) to help the developer decide"
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish_campaign",
            "description": "Finish the lead generation campaign ONLY when the target lead count is fully achieved. DO NOT call this if you have not qualified the requested number of leads; instead formulate a new search query or scroll to discover more leads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "final_summary": {"type": "string", "description": "Summary of campaign outcomes and leads collected"}
                },
                "required": ["final_summary"]
            }
        }
    }
]

