import os
import time
import json
import urllib.request
from datetime import datetime

from src.config import (
    Style,
    log_agent_thought,
    log_tool_call,
    log_tool_result,
    OPENAI_API_KEY,
    BASE_DIR
)
from src.tools.agent_tools import LinkedInAgentTools
from src.tools.schemas import AGENT_TOOLS

def run_autonomous_agent(driver, niche, target_limit, exporter, memory, logger):
    """
    Core ReAct Cognitive Loop for Autonomous BDE Lead Discovery.
    Orchestrates LLM decision making, tool calls, and developer feedback loops.
    """
    active_developer_directives = []
    memory_summary = memory.get_memory_summary()
    for fb in memory_summary.get('user_feedback_guidance', []):
        if fb.get('feedback'):
            active_developer_directives.append(fb.get('feedback'))

    tools_engine = LinkedInAgentTools(
        driver=driver,
        exporter=exporter,
        memory=memory,
        logger=logger,
        active_developer_directives=active_developer_directives
    )

    feedback_section = ""
    if active_developer_directives:
        feedback_section = "- ACTIVE DEVELOPER DIRECTIVES (STRICT COMPLIANCE REQUIRED - TOP PRIORITY):\n" + "\n".join(
            [f"  * \"{directive}\"" for directive in active_developer_directives]
        ) + "\n\n"

    recent_executions = memory_summary.get('recent_executions', [])
    history_section = ""
    if recent_executions:
        history_section = "- ACTUAL RECENT EXECUTION LOG (Real results from previous searches):\n" + "\n".join([
            f"  * Query: '{item.get('query')}' ({item.get('freshness')}) -> Found: {item.get('cards_found', 0)} cards | Qualified: {item.get('qualified_count', 0)} leads | Outcome: {item.get('outcome')}"
            for item in recent_executions
        ]) + "\n\n"

    # Dynamic US Time Context (UTC-5 EST / UTC-8 PST)
    now_utc = datetime.utcnow()
    est_hour = (now_utc.hour - 5) % 24
    pst_hour = (now_utc.hour - 8) % 24
    is_us_night = (est_hour < 8 or est_hour >= 23)

    us_time_guidance = (
        f"- CURRENT US TIME: ~{est_hour:02d}:00 EST / ~{pst_hour:02d}:00 PST ({'NIGHT/OFFLINE in USA' if is_us_night else 'ACTIVE US BUSINESS HOURS'}).\n"
        f"  * Since active US founders are currently {'offline/asleep' if is_us_night else 'active'}, you SHOULD favor 'past-week' freshness to surface high-value posts from earlier in the week.\n"
        f"  * Avoid 'past-24h' during US nighttime as global feeds will be dominated by Asian/European candidates.\n\n"
    )

    system_prompt = f"""You are an elite, fully autonomous Business Development Executive (BDE) AI Agent discovering prospective client leads on LinkedIn.
AGENCY SERVICE / NICHE: {niche}
TARGET GEOGRAPHY: United States ONLY (User is working remotely from India; you must strictly eliminate India, Pakistan, UK, and international leads).
ROLE RESTRICTION: Absolutely NO HR managers, recruiters, staffing agencies, bench sales reps, job seekers, OR INTERMEDIARIES (VCs, investors, accelerators, media curators).
IDEAL CLIENTS: Authentic direct decision-makers (Founders, Co-Founders, CEOs, CTOs, COOs, VPs of Engineering) of their own software/AI startup who are building an MVP or hiring founding engineers.

SESSION PERSISTENT CONTEXT & ISOLATED CSV:
- Current Session CSV: {exporter.csv_path} (Mirrored to: {exporter.current_csv_path})
- Current Session Leads Collected: {len(exporter.leads)} (Session starts fresh with 0 previous leads)
{feedback_section}{history_section}{us_time_guidance}CRITICAL OPERATIONAL INSTRUCTIONS & USA-ONLY SENSING STRATEGY:
1. THE 3 MANDATORY USA LEAD MAGNETS (EMPIRICAL TRUTH):
   LinkedIn content search has NO native country filter. Generic phrases like "building AI MVP team" or "AI startup hiring engineers" match globally and return 90%+ international candidates (India, Africa, Vietnam, Poland).
   To guarantee high-yield USA leads, EVERY query you synthesize MUST incorporate at least one of these 3 US Lead Magnets:
   a) US Tech Hub Anchoring:
      Pair founder intent with specific US metro hubs:
      - "San Francisco" "founding engineer"
      - "Austin" "founding engineer"
      - "NYC" "first engineer"
      - "Bay Area" "building MVP"
      - "Seattle" "stealth AI"
   b) US Startup Accelerators:
      Anchor with top US accelerator batches (95%+ US presence):
      - YC "founding engineer" hiring
      - "Techstars" "founding engineer"
      - "South Park Commons" hiring
   c) US Hiring Constraints & Timezones:
      - "US only" "founding engineer"
      - "US work authorization" "founding engineer"
      - "EST" OR "PST" "first engineer"

2. EXACT PHRASE QUOTING RULES:
   - Enclose exact multi-word cities or compound titles in double quotes: "San Francisco", "Austin", "founding engineer", "first engineer", "US only".
   - Do NOT quote single generic words like engineer or startup (leave unquoted for stem matching).
   - NEVER wrap full sentences in quotes.
   - NEVER put "United States" or "USA" in the query box (it yields 0 results because real US founders don't write "USA").

3. COGNITIVE REASONING & STRATEGY TRANSPARENCY:
   - For EVERY execute_search call, you must explicitly articulate:
     * target_objective: Exactly what prospective client persona or goal you want to achieve with this search.
     * query: The US-anchored search keywords you autonomously synthesized.
     * query_rationale: Strategic reason why these specific keywords were selected for '{niche}'.
     * feasibility_analysis: Will this query achieve the objective, what posts will it attract, and why will it avoid noise and recruiters?
     * developer_feedback_alignment: Explicitly how this query strictly obeys and incorporates all developer feedback.

4. DEVELOPER DIRECTIVES ARE TOP PRIORITY:
   - Always prioritize and strictly obey any developer feedback, guidance, or critique provided. Never repeat a behavior or query that the developer criticized.

5. EARLY FEED BAILOUT:
   - If 2 consecutive cards in a search result fail USA qualification or belong to recruiters/freelancers, STOP scrolling that feed immediately! Formulate an improved query autonomously targeting a different US tech hub or accelerator.

6. DEEP PROFILE LOCATION VERIFICATION:
   - Inspect profile top-card for 100% US presence before qualifying.

7. SINGLE CSV ACCUMULATION:
   - All leads qualified during this session are saved to {exporter.csv_path}. Once you find a lead, the user will be prompted to continue or finish."""

    starting_leads_count = len(exporter.leads)
    target_total_leads = starting_leads_count + target_limit

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Begin autonomous campaign. Current session CSV: '{exporter.csv_path}'. Goal: Discover genuine verified USA decision-maker leads for '{niche}'. Currently {starting_leads_count} leads in this session. Apply the 3 US Lead Magnets (US Tech Hubs, US Accelerators, or US hiring constraints), state your complete cognitive reasoning, and execute search."}
    ]

    is_finished = False
    turn = 0
    max_turns = 40

    while not is_finished and len(exporter.leads) < target_total_leads and turn < max_turns:
        turn += 1

        # Self-healing message sanitization: Ensure every tool_call in assistant messages
        # is immediately followed by its matching tool role messages before any user/assistant message.
        sanitized_messages = []
        msg_idx = 0
        while msg_idx < len(messages):
            m = messages[msg_idx]
            sanitized_messages.append(m)
            if m.get("role") == "assistant" and m.get("tool_calls"):
                expected_ids = {tc["id"] for tc in m["tool_calls"]}
                # Collect trailing tool messages and any interleaved non-tool messages
                next_idx = msg_idx + 1
                matched_tool_msgs = []
                interleaved_msgs = []
                found_ids = set()
                while next_idx < len(messages) and messages[next_idx].get("role") in ["tool", "user", "system"]:
                    if messages[next_idx].get("role") == "tool":
                        tid = messages[next_idx].get("tool_call_id")
                        if tid in expected_ids:
                            found_ids.add(tid)
                            matched_tool_msgs.append(messages[next_idx])
                        else:
                            interleaved_msgs.append(messages[next_idx])
                    else:
                        interleaved_msgs.append(messages[next_idx])
                    next_idx += 1

                sanitized_messages.extend(matched_tool_msgs)
                # Fill any missing tool_call responses with a safe fallback
                for missing_id in (expected_ids - found_ids):
                    sanitized_messages.append({
                        "role": "tool",
                        "tool_call_id": missing_id,
                        "content": json.dumps({"status": "acknowledged", "observation": "Turn completed."}, ensure_ascii=False)
                    })
                sanitized_messages.extend(interleaved_msgs)
                msg_idx = next_idx
                continue
            msg_idx += 1
        messages = sanitized_messages

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "tools": AGENT_TOOLS,
            "tool_choice": "auto",
            "temperature": 0.2
        }

        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                choice = resp_data["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            logger.error(f"OpenAI agent call HTTP error on turn {turn}: {e.code} {e.reason} - {err_body}")
            time.sleep(3)
            continue
        except Exception as e:
            logger.error(f"OpenAI agent call error on turn {turn}: {e}")
            time.sleep(3)
            continue

        thought_content = choice.get("content")
        tool_calls = choice.get("tool_calls") or []

        if thought_content:
            log_agent_thought(thought_content)

        if not tool_calls:
            new_leads_found = len(exporter.leads) - starting_leads_count
            messages.append({"role": "assistant", "content": thought_content or ""})
            messages.append({"role": "user", "content": f"Status: Found {new_leads_found}/{target_limit} new leads this run (Total in session CSV: {len(exporter.leads)}). Call execute_search, scan_and_read_cards, or scroll_feed to proceed."})
            continue

        messages.append({
            "role": "assistant",
            "content": thought_content or "",
            "tool_calls": tool_calls
        })

        pending_user_directives = []
        for tc_idx, tc in enumerate(tool_calls):
            fn = tc["function"]
            fn_name = fn["name"]
            call_id = tc["id"]
            
            try:
                args = json.loads(fn["arguments"])
            except Exception:
                args = {}

            log_tool_call(fn_name, args)

            # ── Dispatch Tool Actions ────────────────────────────
            if fn_name == "execute_search":
                q = args.get("query", "building MVP custom software")
                fresh = args.get("freshness", "past-24h")
                t_obj = args.get("target_objective", "")
                q_rat = args.get("query_rationale", args.get("rationale", ""))
                feas = args.get("feasibility_analysis", "")
                d_align = args.get("developer_feedback_alignment", "")
                result = tools_engine.execute_search(
                    query=q,
                    freshness=fresh,
                    target_objective=t_obj,
                    query_rationale=q_rat,
                    feasibility_analysis=feas,
                    developer_feedback_alignment=d_align
                )
                log_tool_result(result["observation"])

            elif fn_name == "scan_and_read_cards":
                result = tools_engine.scan_and_read_cards()
                log_tool_result(result["observation"])

            elif fn_name == "verify_profile_location":
                card_idx = args.get("card_index", 0)
                a_url = args.get("author_url", "")
                result = tools_engine.verify_profile_location(card_index=card_idx, author_url=a_url)
                log_tool_result(result["observation"])

            elif fn_name == "scroll_feed":
                steps = args.get("steps", 1)
                rat = args.get("rationale", "")
                result = tools_engine.scroll_feed(steps=steps, rationale=rat)
                log_tool_result(result["observation"])

            elif fn_name == "qualify_and_save_lead":
                result = tools_engine.qualify_and_save_lead(
                    card_index=args.get("card_index", 0),
                    author=args.get("author", "Unknown"),
                    profile_url=args.get("profile_url", ""),
                    headline=args.get("headline", ""),
                    role=args.get("role", "Founder"),
                    company=args.get("company", ""),
                    location=args.get("location", "USA"),
                    fit_score=args.get("fit_score", 85),
                    custom_pitch=args.get("custom_pitch", ""),
                    reasoning=args.get("reasoning", "")
                )
                log_tool_result(result["observation"])

                # Interactive prompt immediately when a genuine lead is qualified
                if result.get("status") == "lead_saved_successfully":
                    print("\n" + "=" * 80)
                    print(f"{Style.GREEN}{Style.BOLD}🎯 GENUINE VERIFIED USA LEAD DISCOVERED & SAVED!{Style.RESET}")
                    print(f"   👤 Author: {Style.BOLD}{args.get('author')}{Style.RESET}")
                    print(f"   💼 Role & Company: {args.get('role')} @ {args.get('company') or 'Unknown'}")
                    print(f"   📍 Verified Location: {Style.GREEN}{args.get('location')}{Style.RESET}")
                    print(f"   🔗 Profile URL: {Style.CYAN}{result.get('profile_url')}{Style.RESET}")
                    print(f"   📌 Authentic Post URL: {Style.CYAN}{result.get('post_url')}{Style.RESET}")
                    print(f"   ⭐ Fit Score: {args.get('fit_score')}/100")
                    print(f"   💡 Custom Pitch Hook: {args.get('custom_pitch')}")
                    print(f"   📁 Saved To Session CSV: {Style.CYAN}{exporter.csv_path}{Style.RESET} (Total: {len(exporter.leads)} leads in this session)")
                    print("=" * 80)
                    print(f"{Style.CYAN}{Style.BOLD}👉 Found {len(exporter.leads)} genuine lead(s) in this session. Do you want the agent to continue searching for more?{Style.RESET}")
                    print(f"   {Style.GREEN}[ENTER / Y]{Style.RESET} Yes, search for the next genuine lead in this session (appends to same CSV)")
                    print(f"   {Style.RED}[N / Q]{Style.RESET} No, stop here and wrap up")

                    try:
                        user_resp = input(f"\n{Style.CYAN}Your choice (default: Y to continue): {Style.RESET}").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        user_resp = "n"

                    if user_resp in ["n", "no", "q", "quit", "exit"]:
                        is_finished = True
                    else:
                        target_total_leads += 1  # User wants to find another genuine lead!
                        
                        # Interactive user feedback prompt to refine subsequent lead discovery
                        print(f"\n{Style.YELLOW}{Style.BOLD}💬 DEVELOPER GUIDANCE & SPECIFIC PREFERENCES FOR NEXT SEARCH:{Style.RESET}")
                        print(f"   {Style.DIM}(Share any feedback to guide the AI for the next lead, e.g.:{Style.RESET}")
                        print(f"   {Style.DIM}  • 'Focus strictly on AI/ML or SaaS founders'{Style.RESET}")
                        print(f"   {Style.DIM}  • 'Target Seed or Series A startups in California / NYC'{Style.RESET}")
                        print(f"   {Style.DIM}  • 'Remove quotes from queries'{Style.RESET}")
                        print(f"   {Style.DIM}  • Or press ENTER to continue with default high-intent founder criteria){Style.RESET}")
                        
                        try:
                            user_feedback = input(f"   {Style.BOLD}Developer Guidance > {Style.RESET}").strip()
                        except (EOFError, KeyboardInterrupt):
                            user_feedback = ""

                        if user_feedback:
                            logger.info(f"User provided feedback after lead #{len(exporter.leads)} ({args.get('author')}): '{user_feedback}'")
                            memory.record_user_feedback(lead_author=args.get('author'), feedback=user_feedback)
                            tools_engine.active_developer_directives.append(user_feedback)
                            print(f"   {Style.GREEN}✓ Developer guidance recorded & prioritized for next lead generation!{Style.RESET}\n")
                            
                            pending_user_directives.append({
                                "role": "user",
                                "content": (
                                    f"Lead #{len(exporter.leads)} ({args.get('author')}) was qualified and saved to the session CSV.\n"
                                    f"User confirmed to CONTINUE SEARCHING for the next genuine USA lead.\n"
                                    f"CRITICAL DEVELOPER DIRECTIVE: \"{user_feedback}\".\n"
                                    f"You MUST strictly follow this developer directive in your next search query formulation, reasoning, and candidate selection!\n"
                                    f"Explain your complete cognitive reasoning in execute_search."
                                )
                            })
                        else:
                            pending_user_directives.append({
                                "role": "user",
                                "content": (
                                    f"Lead #{len(exporter.leads)} ({args.get('author')}) was qualified and saved to the session CSV.\n"
                                    f"User confirmed to CONTINUE SEARCHING for the next genuine USA lead.\n"
                                    f"Formulate your next high-intent query (WITHOUT unnecessary double quotes) and state your complete cognitive reasoning."
                                )
                            })

            elif fn_name == "skip_card":
                result = tools_engine.skip_card(
                    card_index=args.get("card_index", 0),
                    author=args.get("author", "Unknown"),
                    rejection_reason=args.get("rejection_reason", "Disqualified")
                )
                log_tool_result(result["observation"])

            elif fn_name == "search_web":
                wq = args.get("query", "")
                wrat = args.get("rationale", "")
                result = tools_engine.search_web(query=wq, rationale=wrat)
                log_tool_result(result["observation"])

            elif fn_name == "propose_code_improvement":
                fp = args.get("file_path", "linkedin_bde_intelligent_pipeline.py")
                t_code = args.get("target_code", "")
                r_code = args.get("replacement_code", "")
                expl = args.get("explanation", "")
                ben = args.get("expected_benefit", "")
                result = tools_engine.propose_code_improvement(
                    file_path=fp,
                    target_code=t_code,
                    replacement_code=r_code,
                    explanation=expl,
                    expected_benefit=ben
                )
                log_tool_result(result["observation"])

            elif fn_name == "ask_developer":
                ques = args.get("question", "")
                ctx = args.get("context", "")
                result = tools_engine.ask_developer(question=ques, context=ctx)
                log_tool_result(result["observation"])

            elif fn_name == "finish_campaign":
                summary = args.get("final_summary", "Campaign finished.")
                is_finished = True
                result = {"status": "campaign_completed", "summary": summary}
                log_agent_thought(f"Campaign Finished: {summary}")

            else:
                result = {"error": f"Unknown tool: {fn_name}"}

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False)
            })

            if is_finished or len(exporter.leads) >= target_total_leads:
                is_finished = True
                # Ensure all remaining tool_calls in this turn get responses so message history remains valid
                for rem_tc in tool_calls[tc_idx + 1:]:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": rem_tc["id"],
                        "content": json.dumps({"status": "skipped", "observation": "Goal reached or campaign wrapped up."}, ensure_ascii=False)
                    })
                break

        # Append developer directives AFTER all tool messages have been appended
        for pud in pending_user_directives:
            messages.append(pud)

    # Save final memory record
    if tools_engine.current_query:
        memory.record_query(
            query=tools_engine.current_query,
            freshness=tools_engine.current_freshness,
            rationale=tools_engine.current_rationale,
            expected_output=getattr(tools_engine, "current_target_objective", ""),
            cards_count=tools_engine.cards_on_current_query,
            qualified_count=tools_engine.qualified_on_current_query
        )

    # Save summary report
    analytics_path = os.path.join(BASE_DIR, "query_performance_analytics.json")
    with open(analytics_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "target_limit": target_limit,
            "qualified_leads_count": len(exporter.leads),
            "skipped_cards_count": tools_engine.skipped_count,
            "total_turns": turn,
            "recent_executions": memory.data.get("execution_history", [])[-10:]
        }, f, indent=2, ensure_ascii=False)

    return tools_engine

