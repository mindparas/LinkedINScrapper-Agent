#!/usr/bin/env python3
"""
================================================================================
  AUTONOMOUS AI BDE LEAD DISCOVERY AGENT — STANDALONE USER LAUNCHER
================================================================================
Designed for independent, hands-free operation:
  • Prompt asks only for the desired number of leads (and optional time limit).
  • AI executes everything autonomously: query formulation, top-card USA 
    verification, active commercial buying intent evaluation, and shortlink capture.
  • Automatically rotates queries across top US tech hubs and accelerators.
  • Stops automatically when target lead count is achieved or time limit expires.
  • Outputs pristine CSV & JSON reports into exports/ directory.
================================================================================
"""

import os
import sys
import time
import argparse
from datetime import datetime

# Set path to include python-agent directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from src.config import Style, setup_file_logger, BASE_DIR, OPENAI_API_KEY
from src.storage import LiveLeadExporter, AgentMemory
from src.browser import setup_stealth_driver, verify_or_prompt_login
from src.agent.runner import run_autonomous_agent


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Autonomous USA BDE Lead Discovery Agent (100% Hands-Free)"
    )
    parser.add_argument(
        "-n", "--leads",
        type=int,
        default=None,
        help="Target number of genuine USA leads to find (e.g. 1, 3, 5)"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=int,
        default=None,
        help="Max search duration in minutes (e.g. 15). Set 0 for unlimited."
    )
    parser.add_argument(
        "--niche",
        type=str,
        default="custom software & AI MVP engineering",
        help="Agency niche/service offered (default: 'custom software & AI MVP engineering')"
    )
    parser.add_argument(
        "--keep-browser",
        action="store_true",
        help="Keep browser window open after run for manual inspection"
    )
    return parser.parse_args()


def display_banner():
    print(f"\n{Style.CYAN}{Style.BOLD}" + "=" * 80)
    print(" 🚀 AUTONOMOUS USA BDE LEAD DISCOVERY AGENT")
    print("    100% Autonomous | Strict USA Filter | Verified Intent | Authentic URLs")
    print("=" * 80 + f"{Style.RESET}\n")


def print_leads_summary_table(leads):
    if not leads:
        print(f"\n{Style.YELLOW}No leads were qualified during this run.{Style.RESET}\n")
        return

    print("\n" + "=" * 80)
    print(f"{Style.GREEN}{Style.BOLD}🎉 CAMPAIGN COMPLETED: DISCOVERED {len(leads)} VERIFIED USA CLIENT LEADS{Style.RESET}")
    print("=" * 80)
    for idx, lead in enumerate(leads, 1):
        author = lead.get("Author Name") or lead.get("Author") or "Unknown"
        role = lead.get("Title / Headline") or lead.get("Role") or "Founder"
        company = lead.get("Company Name") or lead.get("Company") or "Startup"
        loc = lead.get("Verified Location") or lead.get("Location") or "USA"
        score = lead.get("Fit Score") or "N/A"
        post_url = lead.get("Post URL") or "N/A"
        profile_url = lead.get("Profile URL") or "N/A"
        intent = lead.get("Commercial Intent Category") or lead.get("Buying Intent Signal") or ""
        conn_note = lead.get("LinkedIn Connection Note (<300 chars)") or lead.get("Custom Outreach Hook") or ""
        tech = lead.get("Target Tech Stack") or ""

        print(f" {Style.BOLD}[#{idx}] {author}{Style.RESET} — {role}")
        print(f"      🏢 Company: {company} | 📍 Location: {Style.GREEN}{loc}{Style.RESET}")
        print(f"      ⭐ Fit Score: {score}/100 | 🔥 Intent: {intent}")
        if tech:
            print(f"      💻 Tech Stack: {tech}")
        print(f"      📌 Authentic Post URL: {Style.CYAN}{post_url}{Style.RESET}")
        print(f"      🔗 Profile URL:        {Style.CYAN}{profile_url}{Style.RESET}")
        if conn_note:
            print(f"      ✉️  BDE Connection Note: {Style.YELLOW}\"{conn_note}\"{Style.RESET}")
        print("-" * 80)


def main():
    display_banner()

    # Pre-flight check: Verify OpenAI API key
    if not OPENAI_API_KEY:
        print(f"{Style.RED}❌ Error: OPENAI_API_KEY not found in environment or .env file.{Style.RESET}")
        print("Please configure your API key in python-agent/.env before running.")
        sys.exit(1)

    args = parse_arguments()

    # Lead target count prompt
    if args.leads is not None:
        target_leads = args.leads
    else:
        try:
            val = input(f"{Style.BOLD}👉 How many verified USA leads do you want? [default: 3]: {Style.RESET}").strip()
            target_leads = int(val) if val.isdigit() and int(val) > 0 else 3
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            sys.exit(0)

    # Runtime duration prompt
    if args.timeout is not None:
        timeout_minutes = args.timeout
    else:
        try:
            t_val = input(f"{Style.BOLD}⏱️ Max search time in minutes (press ENTER for default 15 min, or 0 for unlimited): {Style.RESET}").strip()
            if t_val == "0":
                timeout_minutes = 0
            elif t_val.isdigit() and int(t_val) > 0:
                timeout_minutes = int(t_val)
            else:
                timeout_minutes = 15
        except (EOFError, KeyboardInterrupt):
            timeout_minutes = 15

    max_duration_seconds = (timeout_minutes * 60) if timeout_minutes > 0 else None

    # Always enforce non-interactive autonomous mode
    os.environ["NON_INTERACTIVE"] = "1"

    print(f"\n{Style.GREEN}✓ Mission parameters locked:{Style.RESET}")
    print(f"  • Target Leads: {Style.BOLD}{target_leads}{Style.RESET}")
    print(f"  • Max Duration: {Style.BOLD}{f'{timeout_minutes} minutes' if timeout_minutes > 0 else 'Unlimited (until leads found)'}{Style.RESET}")
    print(f"  • Agency Niche: {Style.BOLD}{args.niche}{Style.RESET}")
    print(f"  • Mode:         {Style.CYAN}100% Fully Autonomous (Zero manual input required){Style.RESET}\n")

    logger, log_file_path = setup_file_logger()
    memory = AgentMemory()
    exporter = LiveLeadExporter()

    print(f"📁 Session CSV Initialized: {Style.CYAN}{exporter.csv_path}{Style.RESET}")
    print(f"📁 Latest Mirror CSV:       {Style.CYAN}{exporter.current_csv_path}{Style.RESET}")

    profile_dir = os.path.join(BASE_DIR, "linkedin_chrome_profile")
    driver = setup_stealth_driver(profile_dir)

    try:
        verify_or_prompt_login(driver, logger)

        print(f"\n{Style.BOLD}🤖 Starting Autonomous Lead Search Engine...{Style.RESET}\n")
        start_time = time.time()

        run_autonomous_agent(
            driver=driver,
            niche=args.niche,
            target_limit=target_leads,
            exporter=exporter,
            memory=memory,
            logger=logger,
            max_duration_seconds=max_duration_seconds
        )

        total_elapsed = round((time.time() - start_time) / 60, 1)
        print(f"\n{Style.GREEN}⏱️ Search completed in {total_elapsed} minutes.{Style.RESET}")

        # Display final results table
        print_leads_summary_table(exporter.leads)

        print(f"\n📁 Results saved to:")
        print(f"   • Dedicated CSV:  {Style.CYAN}{exporter.csv_path}{Style.RESET}")
        print(f"   • Dedicated JSON: {Style.CYAN}{exporter.json_path}{Style.RESET}")
        print(f"   • Latest Pointer: {Style.CYAN}{exporter.current_csv_path}{Style.RESET}")
        print(f"   • Session Log:    {Style.CYAN}{log_file_path}{Style.RESET}\n")

    except Exception as e:
        logger.exception("Fatal error during autonomous lead run:")
        print(f"\n{Style.RED}❌ Run error: {e}{Style.RESET}")
    finally:
        if args.keep_browser:
            print(f"{Style.YELLOW}Browser remains open for inspection (--keep-browser). Press ENTER to close: {Style.RESET}")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass

        try:
            driver.quit()
        except Exception:
            pass
        print(f"{Style.BLUE}Browser closed cleanly.{Style.RESET}\n")


if __name__ == "__main__":
    main()
