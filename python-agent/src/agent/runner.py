import os
import time
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.config import (
    Style,
    log_agent_thought,
    log_tool_call,
    log_tool_result,
    BASE_DIR
)
from src.tools.schemas import AGENT_TOOLS
from src.agent.context import compact_tool_result, window_messages
from src.agent.mission import DEFAULT_MISSION
from src import llm
from src.metrics import RunMetrics

def run_autonomous_agent(driver, niche, target_limit, exporter, memory, logger, max_duration_seconds=None, mission=None, print_report=True):
    """
    Core ReAct Cognitive Loop for Autonomous BDE Lead Discovery.
    Orchestrates LLM decision making, sensor actuation, and self-debugging navigation.
    """
    from src.tools.agent_tools import LinkedInAgentTools
    active_developer_directives = []
    mission = mission or DEFAULT_MISSION
    metrics = RunMetrics(mission=mission, target=target_limit, starting_leads=len(exporter.leads))

    tools_engine = LinkedInAgentTools(
        driver=driver,
        exporter=exporter,
        memory=memory,
        logger=logger,
        active_developer_directives=active_developer_directives,
        mission=mission,
        metrics=metrics
    )

    # Dynamic US Time Context (DST-aware with Windows fallback)
    try:
        from zoneinfo import ZoneInfo
        now_utc = datetime.now(timezone.utc)
        est_hour = now_utc.astimezone(ZoneInfo("America/New_York")).hour
        pst_hour = now_utc.astimezone(ZoneInfo("America/Los_Angeles")).hour
    except Exception:
        now_utc = datetime.now(timezone.utc)
        est_hour = (now_utc.hour - 5) % 24
        pst_hour = (now_utc.hour - 8) % 24
    is_us_night = (est_hour < 8 or est_hour >= 23)

    if mission.is_default:
        system_prompt = f"""You are an autonomous BDE lead-discovery agent for an Indian software/AI development agency ({niche}).
GOAL: find {target_limit} US founders/CTOs/VPs who posted a CURRENT need for outside engineering help (MVP build, dev shop/agency, contractors, technical co-founder, engineering hires).
Session CSV: {exporter.csv_path}

HOW YOU WORK
- Search with execute_search, then scan_and_read_cards. Each card already carries a verdict from a dedicated lead judge and many are profile-verified. Code auto-rejects recruiters, agencies, job seekers and non-US authors; never re-evaluate those.
- qualify_and_save_lead only for cards with judge.category BUYER (confidence >= 0.7) whose author is a decision maker; the tool enforces this. Use verify_profile_location only if a promising card has no verified_location.
- skip_card only with a specific reason citing evidence.

QUERY STRATEGY & ADAPTIVE PATTERN SHIFTING
- PROPER QUERY FORMULATION: Keep queries concise (2-3 words). Use authentic founder vernacular ('building our MVP', 'hiring founding engineer', 'recommend a dev shop', 'Austin building our MVP').
- NEVER OVER-SPECIFY: NEVER combine 3+ constraints (e.g. NEVER search 'City + Niche + Intent' like 'Pear VC fintech looking for dev shop'—LinkedIn returns 0 results for over-constrained phrases). Maximum 2 components: [US Hub/Accelerator] + [Intent Phrase] or bare [Intent Phrase].
- DUAL TIMEFRAME CHECKING: The search tool automatically inspects BOTH 'past-24h' and 'past-week' for every search. You do not need to worry about missing weekly posts.
- BRAIN PATTERN SHIFTING: When a query yields 0 results across both timeframes, do NOT repeat that same failed phrase for other cities. Immediately shift your search pattern to a different archetype (e.g., pivot from agency search to MVP build, or from MVP build to founding engineer hiring) and prefer the planner's suggested query.
- Queries must be natural and unquoted; never include 'USA' or 'United States'.
- The state block gives a SUGGESTED NEXT QUERY chosen by a learning planner from real results; use it unless you have clearly better evidence. The planner rewrites its strategy after repeated misses and may replace a query you pick.
- Stop with finish_campaign only when {target_limit} leads are saved, or when told HALTED."""
    else:
        loc_rule = ("Code verifies each author's profile location and auto-rejects non-US authors; never re-evaluate those."
                    if mission.needs_us else "There is NO location filter for this mission; do not reject anyone for location.")
        dm_rule = ("the author must be a decision maker (the tool enforces this)" if mission.require_decision_maker
                   else "any author type is acceptable")
        system_prompt = f"""You are an autonomous lead-discovery agent for: {niche}.
MISSION (set by the user): {mission.summary}
User's words: "{mission.raw_intent[:400]}"
Qualifying posts: {'; '.join(mission.post_types) or 'see mission'}.
Must have: {'; '.join(mission.must_have) or 'n/a'}. Must NOT match: {'; '.join(mission.exclude) or 'n/a'}.
GOAL: find {target_limit} authors whose post matches this mission.
Session CSV: {exporter.csv_path}

HOW YOU WORK
- Search with execute_search, then scan_and_read_cards. Each card carries a verdict from a dedicated lead judge that applies the mission above (category BUYER means "matches the mission"). {loc_rule}
- qualify_and_save_lead only for cards with judge.category BUYER (confidence >= 0.7); {dm_rule}. Use verify_profile_location only if a promising card has no verified_location and the mission needs a location.
- skip_card only with a specific reason citing evidence from the post.

QUERY STRATEGY
- Queries are short (2-4 words), natural, unquoted phrases that the target authors would actually write in such a post. Start from the planner's suggested queries; they were derived from the mission.
- Maximum 2 components per query. No boolean operators, no quotes{', no country names' if mission.needs_us else ''}.
- The search tool checks BOTH 'past-24h' and 'past-week' automatically.
- When a query yields 0 results or off-target posts, shift to a different phrasing family rather than repeating it; prefer the planner's suggestion.
- The state block gives a SUGGESTED NEXT QUERY chosen by a learning planner from real results; use it unless you have clearly better evidence. The planner rewrites its strategy after repeated misses and may replace a query you pick.
- Stop with finish_campaign only when {target_limit} leads are saved, or when told HALTED."""

    agent_tools_schema = _tools_for_mission(mission)
    starting_leads_count = len(exporter.leads)
    target_total_leads = starting_leads_count + target_limit

    initial_query = tools_engine.get_next_recommended_query()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (f"Begin. Find {target_limit} verified US leads. Suggested first query: '{initial_query}'."
                                     if mission.is_default else
                                     f"Begin. Find {target_limit} leads for the mission: {mission.title}. Suggested first query: '{initial_query}'.")}
    ]

    is_finished = False
    turn = 0
    if max_duration_seconds:
        tools_engine.deadline = time.time() + max_duration_seconds
    max_turns = max(80, target_limit * 30)
    start_time = time.time()

    stop_reason = ""
    try:
        while not is_finished and len(exporter.leads) < target_total_leads and turn < max_turns:
            elapsed = time.time() - start_time
            if max_duration_seconds and elapsed >= max_duration_seconds:
                logger.info(f"Time limit of {max_duration_seconds/60:.1f} minutes reached. Stopping agent.")
                print(f"\n{Style.YELLOW}{Style.BOLD}⏱️ TIME LIMIT REACHED: {max_duration_seconds/60:.1f} minutes elapsed. Wrapping up and saving collected leads...{Style.RESET}")
                is_finished = True
                stop_reason = "time_limit"
                break

            if tools_engine.halt_reason:
                print(f"\n{Style.RED}{Style.BOLD}🛑 SAFETY HALT: {tools_engine.halt_reason}. Stopping to protect your LinkedIn account; leads found so far are saved.{Style.RESET}")
                logger.error(f"Run halted: {tools_engine.halt_reason}")
                stop_reason = "safety_halt"
                break

            if tools_engine.stagnation_reason:
                print(f"\n{Style.YELLOW}{Style.BOLD}🧭 STOPPING EARLY: {tools_engine.stagnation_reason}. "
                      f"Further searching with this intent is unlikely to help; see the report for what the strategist learned.{Style.RESET}")
                logger.warning(f"Run stopped for stagnation: {tools_engine.stagnation_reason}")
                stop_reason = "stagnation"
                break

            turn += 1

            # Self-healing message sanitization
            sanitized_messages = []
            msg_idx = 0
            while msg_idx < len(messages):
                m = messages[msg_idx]
                sanitized_messages.append(m)
                if m.get("role") == "assistant" and m.get("tool_calls"):
                    expected_ids = {tc["id"] for tc in m["tool_calls"]}
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

            messages = window_messages(messages)
            state_msg = {"role": "user", "content": "STATE\n" + tools_engine.state_summary(
                target_total_leads, len(exporter.leads))}
            try:
                resp_data = llm.agent_step(messages[:2] + [state_msg] + messages[2:], agent_tools_schema)
                choice = resp_data["choices"][0]["message"]
                metrics.agent_llm(resp_data.get("usage"))
            except Exception as e:
                metrics.agent_llm(ok=False)
                err_body = ""
                if hasattr(e, "read"):
                    try:
                        err_body = e.read().decode("utf-8")
                    except Exception:
                        pass
                logger.error(f"Agent LLM call error on turn {turn}: {llm.describe_error(e)} {err_body}")
                time.sleep(3)
                continue

            thought_content = choice.get("content")
            tool_calls = choice.get("tool_calls") or []

            if thought_content:
                log_agent_thought(thought_content)

            if not tool_calls:
                new_leads_found = len(exporter.leads) - starting_leads_count
                messages.append({"role": "assistant", "content": thought_content or ""})
                messages.append({"role": "user", "content": f"Status: Found {new_leads_found}/{target_limit} genuine leads (Total in session CSV: {len(exporter.leads)}). Call execute_search, scan_and_read_cards, or scroll_feed to proceed."})
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
                metrics.tool(fn_name)

                # ── Dispatch Tool Actions ────────────────────────────
                if fn_name == "execute_search":
                    q = args.get("query", initial_query)
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
                        fit_score=args.get("fit_score", 90),
                        custom_pitch=args.get("custom_pitch", ""),
                        reasoning=args.get("reasoning", ""),
                        buying_intent_signal=args.get("buying_intent_signal", "")
                    )
                    log_tool_result(result["observation"])

                    if result.get("status") == "lead_saved_successfully":
                        total_collected = len(exporter.leads)
                        print("\n" + "=" * 80)
                        print(f"{Style.GREEN}{Style.BOLD}🎯 GENUINE VERIFIED USA SALES LEAD DISCOVERED & SAVED! [#{total_collected}/{target_total_leads}]{Style.RESET}")
                        print(f"   👤 Author: {Style.BOLD}{args.get('author')}{Style.RESET}")
                        print(f"   💼 Role & Company: {args.get('role')} @ {args.get('company') or 'Unknown'}")
                        print(f"   📍 Verified Location: {Style.GREEN}{args.get('location')}{Style.RESET}")
                        print(f"   🔥 Buying Intent: {Style.YELLOW}{result.get('buying_intent_signal')}{Style.RESET}")
                        print(f"   🔗 Profile URL: {Style.CYAN}{result.get('profile_url')}{Style.RESET}")
                        print(f"   📌 Authentic Post URL: {Style.CYAN}{result.get('post_url')}{Style.RESET}")
                        print(f"   ⭐ Fit Score: {args.get('fit_score')}/100")
                        print(f"   📁 Saved To CSV: {Style.CYAN}{exporter.csv_path}{Style.RESET}")
                        print("=" * 80)

                        if total_collected >= target_total_leads:
                            is_finished = True
                            print(f"\n{Style.GREEN}{Style.BOLD}🏆 Target campaign goal of {target_limit} leads reached! Wrapping up...{Style.RESET}\n")
                        else:
                            pending_user_directives.append({
                                "role": "user",
                                "content": (
                                    f"Lead #{total_collected} ({args.get('author')}) was qualified and saved to session CSV.\n"
                                    f"Goal: {total_collected}/{target_total_leads} leads collected.\n"
                                    f"Continue autonomous search for lead #{total_collected + 1}. Formulate your next strategic query or scan remaining cards."
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
                    fp = args.get("file_path", "")
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
                    if len(exporter.leads) < target_total_leads:
                        next_rec = tools_engine.get_next_recommended_query()
                        result = {
                            "status": "target_not_reached",
                            "observation": f"CANNOT FINISH: Target lead count not achieved yet ({len(exporter.leads)}/{target_total_leads} leads qualified). You must continue searching: formulate a new search query targeting another US tech hub (e.g. '{next_rec}') or scroll down to load more cards."
                        }
                        log_agent_thought(f"Campaign Finish rejected: Target lead count ({target_total_leads}) not achieved yet.")
                    else:
                        summary = args.get("final_summary", "Campaign finished.")
                        is_finished = True
                        result = {"status": "campaign_completed", "summary": summary}
                        log_agent_thought(f"Campaign Finished: {summary}")

                else:
                    result = {"error": f"Unknown tool: {fn_name}"}

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": compact_tool_result(fn_name, result)
                })

                if is_finished or len(exporter.leads) >= target_total_leads:
                    is_finished = True
                    for rem_tc in tool_calls[tc_idx + 1:]:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": rem_tc["id"],
                            "content": json.dumps({"status": "skipped", "observation": "Goal reached or campaign wrapped up."}, ensure_ascii=False)
                        })
                    break

            for pud in pending_user_directives:
                messages.append(pud)

    except KeyboardInterrupt:
        stop_reason = "interrupted"
        raise
    except BaseException:
        stop_reason = "error"
        raise
    finally:
        report = None
        try:
            report, report_text, report_path = _finish_run(
                tools_engine, exporter, metrics, stop_reason, is_finished, turn, max_turns, target_total_leads)
            tools_engine.run_report_text = report_text + (f"\n   Full metrics report: {Style.CYAN}{report_path}{Style.RESET}\n" if report_path else "")
            if print_report or stop_reason in ("error", "interrupted"):
                print(tools_engine.run_report_text)
        except Exception as report_err:
            logger.error(f"Could not build run metrics: {report_err}")


    # Save final memory record
    tools_engine._finalize_query()

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

    tools_engine.run_report = report
    return tools_engine


def _tools_for_mission(mission):
    """The tool schemas are written for the default mission; give the search tool mission-neutral wording otherwise."""
    if mission.is_default:
        return AGENT_TOOLS
    import copy
    tools = copy.deepcopy(AGENT_TOOLS)
    for t in tools:
        fn = t["function"]
        if fn["name"] == "execute_search":
            fn["description"] = "Execute a LinkedIn content search for posts matching the mission."
            fn["parameters"]["properties"]["query"]["description"] = (
                "Search phrase that the target authors would write in such a post, preferably exactly the one suggested by the "
                "planner. Either 2-4 plain keywords, or an exact phrase of 3-6 words wrapped in double quotes. No boolean operators.")
        elif fn["name"] == "qualify_and_save_lead":
            fn["description"] = "Saves a post that matches the mission (judge category BUYER) with its exact post URL to CSV and JSON."
    return tools


def _finish_run(tools_engine, exporter, metrics, stop_reason, is_finished, turn, max_turns, target_total_leads):
    """Derive why the run ended, build the performance report, print it and persist it."""
    tools_engine._finalize_query()
    if not stop_reason:
        if tools_engine.stagnation_reason:
            stop_reason = "stagnation"
        elif tools_engine.halt_reason:
            stop_reason = "safety_halt"
        elif len(exporter.leads) >= target_total_leads:
            stop_reason = "target_reached"
        elif is_finished:
            stop_reason = "agent_finished"
        elif turn >= max_turns:
            stop_reason = "turn_cap"
    prev = metrics.previous_run()
    report = metrics.build_report(
        judge=tools_engine.judge, usage=tools_engine.usage, leads_total=len(exporter.leads),
        stop_reason=stop_reason, turns=turn, halt_reason=tools_engine.halt_reason or tools_engine.stagnation_reason,
        engine=tools_engine.engine)
    path = metrics.save(report)
    return report, metrics.render(report, prev), path
