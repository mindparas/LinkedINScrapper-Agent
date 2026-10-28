import os
import sys

from src.config import Style, setup_file_logger, BASE_DIR
from src.storage import LiveLeadExporter, AgentMemory
from src.browser import setup_stealth_driver, verify_or_prompt_login
from src.agent.runner import run_autonomous_agent

def main():
    """
    Main CLI entry point for the LinkedIn Autonomous AI BDE Discovery Agent.
    Manages persistent browser lifecycles, interactive feedback rounds,
    and multi-turn campaign executions.
    """
    print(f"\n{Style.CYAN}{Style.BOLD}" + "=" * 80)
    print(" 🚀 AUTONOMOUS AI BDE LEAD DISCOVERY AGENT (V3)")
    print("    Persistent Browser | Exact CSV | Profile Verification | Persistent Memory")
    print("=" * 80 + f"{Style.RESET}\n")

    logger, log_file_path = setup_file_logger()
    print(f"📄 Detailed session action log saving to: {Style.YELLOW}{log_file_path}{Style.RESET}")

    memory = AgentMemory()
    print(f"🧠 Persistent memory loaded from: {Style.CYAN}{memory.filepath}{Style.RESET}")

    # Agency Niche (Direct launch; press ENTER for default)
    try:
        niche_input = input(f"\n{Style.CYAN}Enter your agency service/niche (press ENTER for 'custom software & AI MVP engineering'): {Style.RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        niche_input = ""
    niche = niche_input if niche_input else "custom software & AI MVP engineering"

    # Search directly until at least 1 genuine lead is found, then interactively prompt user
    target_limit = 1

    profile_dir = os.path.join(BASE_DIR, "linkedin_chrome_profile")
    # Single Dedicated Session CSV Exporter: maintains 1 fresh CSV for this session, ignores previous CSV files
    exporter = LiveLeadExporter()
    print(f"📁 New Session CSV Initialized: {Style.CYAN}{exporter.csv_path}{Style.RESET} (Starts fresh with 0 leads)")
    print(f"📁 Latest Session Pointer: {Style.CYAN}{exporter.current_csv_path}{Style.RESET}")

    # Launch Chrome Driver with persistent profile
    driver = setup_stealth_driver(profile_dir)

    try:
        verify_or_prompt_login(driver, logger)

        round_num = 1
        while True:
            print("\n" + "=" * 80)
            print(f"{Style.BOLD}🤖 [ROUND {round_num}] AUTONOMOUS BDE LEAD DISCOVERY AGENT ACTIVATED{Style.RESET}")
            print(f"🎯 Mission: Discover verified genuine USA leads for '{niche}'")
            print(f"📋 Single Session CSV: {Style.CYAN}{exporter.csv_path}{Style.RESET} (Currently {len(exporter.leads)} leads in this session)")
            print("=" * 80)

            # Run the autonomous agent
            run_autonomous_agent(
                driver=driver,
                niche=niche,
                target_limit=target_limit,
                exporter=exporter,
                memory=memory,
                logger=logger
            )

            print(f"\n{Style.GREEN}{Style.BOLD}🎉 ROUND {round_num} COMPLETED!{Style.RESET}")
            print(f"📁 Session Qualified Leads CSV: {Style.CYAN}{exporter.csv_path}{Style.RESET} (Total: {len(exporter.leads)} leads accumulated in this session)")
            print(f"📁 Session Qualified Leads JSON: {Style.CYAN}{exporter.json_path}{Style.RESET}")
            print(f"📁 Latest Current Session CSV: {Style.CYAN}{exporter.current_csv_path}{Style.RESET}")
            print(f"🧠 Updated Memory File: {Style.CYAN}{memory.filepath}{Style.RESET}")
            print(f"📄 Full Session Action Log: {Style.CYAN}{log_file_path}{Style.RESET}\n")

            # Same-Session Interactive Re-run Menu
            print("=" * 80)
            print(f"{Style.CYAN}{Style.BOLD}⚡ SAME-SESSION CONTROL MENU (Browser Remains Active & Logged In):{Style.RESET}")
            print(f"   {Style.GREEN}[1 / ENTER]{Style.RESET} Continue / Re-run lead discovery in this SAME session (Appends to same session CSV)")
            print(f"   {Style.YELLOW}[2]{Style.RESET} Change agency niche or target lead count for next round")
            print(f"   {Style.BLUE}[3]{Style.RESET} View current session leads & memory summary")
            print(f"   {Style.RED}[4 / Q]{Style.RESET} Quit & Close Browser")
            print("=" * 80)

            try:
                choice = input(f"\n{Style.CYAN}Choose an option (press ENTER to re-run in same session): {Style.RESET}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "q"

            if choice in ["4", "q", "quit", "exit"]:
                print(f"\n{Style.YELLOW}Closing lead generation session...{Style.RESET}")
                break

            elif choice == "2":
                try:
                    new_niche = input(f"\nEnter new agency niche/service (leave empty to keep '{niche}'): ").strip()
                    if new_niche:
                        niche = new_niche
                    new_count = input(f"Enter target number of additional leads to collect (default: 5): ").strip()
                    if new_count.isdigit() and int(new_count) > 0:
                        target_limit = int(new_count)
                except (EOFError, KeyboardInterrupt):
                    pass
                round_num += 1

            elif choice == "3":
                mem_sum = memory.get_memory_summary()
                print(f"\n{Style.BOLD}🧠 EMPIRICAL AGENT MEMORY LOG ({memory.filepath}):{Style.RESET}")
                print(f"  • Total Real Searches Executed: {mem_sum['total_queries_tested']}")
                print(f"  • Recent AI Search Executions ({len(mem_sum['recent_executions'])}):")
                for ex in mem_sum['recent_executions']:
                    print(f"      - Query: '{ex.get('query')}' ({ex.get('freshness')}) | Cards: {ex.get('cards_found', 0)} | Leads Qualified: {ex.get('qualified_count', 0)}")
                    print(f"        Outcome: {ex.get('outcome')}")
                if mem_sum['user_feedback_guidance']:
                    print(f"\n  • Developer Guidance Directives ({len(mem_sum['user_feedback_guidance'])}):")
                    for dg in mem_sum['user_feedback_guidance']:
                        print(f"      - [{dg.get('timestamp', '')[:19]}] {dg.get('feedback')}")
                try:
                    input(f"\n{Style.DIM}Press ENTER to return to menu...{Style.RESET}")
                except (EOFError, KeyboardInterrupt):
                    pass
                continue

            else:
                round_num += 1
                target_limit = 1

    except Exception as e:
        logger.exception("Fatal error during agent run:")
        print(f"\n{Style.RED}❌ Agent error: {e}{Style.RESET}")
    finally:
        print("\n" + "=" * 80)
        print(f"{Style.GREEN}{Style.BOLD}🌐 PERSISTENT BROWSER WINDOW REMAINS OPEN FOR YOUR INSPECTION.{Style.RESET}")
        print("You can view the LinkedIn tabs, explore search results, and inspect verified profiles.")
        print("=" * 80)
        try:
            input(f"\n{Style.DIM}Press ENTER here in terminal whenever you are ready to close the browser session...{Style.RESET}")
        except (EOFError, KeyboardInterrupt):
            pass
        try:
            driver.quit()
        except Exception:
            pass
        print(f"{Style.BLUE}Browser closed cleanly. Session saved in profile.{Style.RESET}")

if __name__ == "__main__":
    main()

