import os
import sys
import time
import json
import random
import urllib.parse
import py_compile
from selenium.webdriver.common.by import By

from src.config import Style, log_tool_result, log_qualified, log_skipped, BASE_DIR
from src.verification import (
    clean_linkedin_boolean_query,
    parse_post_age,
    is_verified_usa_location,
    verify_bde_lead_authenticity,
)
from src.browser import search_web_api

class LinkedInAgentTools:
    """
    Sensor and Actuator tool suite executed by the Autonomous AI Agent.
    Interacts directly with the active Selenium Chrome driver.
    """
    def __init__(self, driver, exporter, memory, logger, active_developer_directives=None):
        self.driver = driver
        self.exporter = exporter
        self.memory = memory
        self.logger = logger
        self.evaluated_fingerprints = set()
        self.active_developer_directives = active_developer_directives if active_developer_directives is not None else []
        
        # Pre-seed fingerprints strictly with THIS session's leads (starts 100% clean)
        for l in self.exporter.leads:
            auth = (l.get("Author Name") or "").strip().lower()
            purl = (l.get("Profile URL") or "").strip().lower().split('?')[0].rstrip('/')
            if auth:
                self.evaluated_fingerprints.add(auth)
            if purl:
                self.evaluated_fingerprints.add(purl)
                
        self.current_query = ""
        self.current_freshness = "past-24h"
        self.current_target_objective = ""
        self.current_rationale = ""
        self.current_feasibility = ""
        self.current_developer_alignment = ""
        self.scroll_count_on_query = 0
        self.skipped_count = 0
        self.cards_on_current_query = 0
        self.qualified_on_current_query = 0
        self.consecutive_non_usa_count = 0

    @property
    def current_expected_output(self):
        return self.current_target_objective

    @current_expected_output.setter
    def current_expected_output(self, val):
        self.current_target_objective = val

    def execute_search(
        self,
        query: str,
        freshness: str = "past-24h",
        target_objective: str = "",
        query_rationale: str = "",
        feasibility_analysis: str = "",
        developer_feedback_alignment: str = "",
        rationale: str = "",
        expected_output: str = ""
    ):
        query_rationale = query_rationale or rationale
        target_objective = target_objective or expected_output

        # Wrap up previous query stats in memory if exists
        if self.current_query:
            self.memory.record_query(
                query=self.current_query,
                freshness=self.current_freshness,
                rationale=self.current_rationale,
                expected_output=self.current_target_objective,
                cards_count=self.cards_on_current_query,
                qualified_count=self.qualified_on_current_query
            )

        self.scroll_count_on_query = 0
        self.cards_on_current_query = 0
        self.qualified_on_current_query = 0
        self.consecutive_non_usa_count = 0
        clean_q = clean_linkedin_boolean_query(query)
        self.current_query = clean_q
        self.current_freshness = freshness if freshness in ["past-24h", "past-week"] else "past-24h"
        self.current_target_objective = target_objective
        self.current_rationale = query_rationale
        self.current_feasibility = feasibility_analysis
        self.current_developer_alignment = developer_feedback_alignment

        # Prominently display the Agent Cognitive Reasoning Card
        print("\n" + "=" * 80)
        print(f"{Style.CYAN}{Style.BOLD}🧠 [AGENT REASONING & SEARCH STRATEGY]{Style.RESET}")
        print(f"🎯 {Style.BOLD}Target Objective (What it wants to achieve):{Style.RESET}\n   {target_objective or 'Targeting authentic founders building MVPs/software'}")
        print(f"🔍 {Style.BOLD}LinkedIn Search Query:{Style.RESET} {Style.YELLOW}'{clean_q}'{Style.RESET} ({self.current_freshness})")
        print(f"💡 {Style.BOLD}Strategic Rationale:{Style.RESET}\n   {query_rationale or 'Unquoted natural intent query for high recall'}")
        print(f"🚀 {Style.BOLD}Feasibility Assessment (Will it achieve the goal?):{Style.RESET}\n   {feasibility_analysis or 'Matches active founder vernacular while filtering out recruiters'}")
        if developer_feedback_alignment:
            print(f"💬 {Style.BOLD}Developer Feedback Integrated:{Style.RESET}\n   {Style.GREEN}{developer_feedback_alignment}{Style.RESET}")
        print("=" * 80)

        # Developer Live Steering Point BEFORE navigating on LinkedIn
        print(f"\n{Style.CYAN}{Style.BOLD}💬 [DEVELOPER INTERACTION & STEERING]:{Style.RESET}")
        print(f"   {Style.DIM}(Press ENTER to run this search, or type your instructions to steer/improve it){Style.RESET}")
        try:
            dev_hint = input(f"   {Style.BOLD}Developer Guidance > {Style.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            dev_hint = ""

        if dev_hint:
            self.logger.info(f"Developer steered agent during search formulation: '{dev_hint}'")
            self.memory.record_user_feedback(lead_author="Search Formulation", feedback=dev_hint)
            self.active_developer_directives.append(dev_hint)
            print(f"   {Style.GREEN}✓ Developer guidance recorded: '{dev_hint}'{Style.RESET}\n")
            return {
                "status": "developer_guidance_provided",
                "developer_guidance": dev_hint,
                "observation": (
                    f"DEVELOPER OVERRIDE: The developer reviewed your proposed query and gave direct guidance: '{dev_hint}'. "
                    f"Do NOT execute '{clean_q}'. You MUST immediately formulate a new search query strictly incorporating this feedback. "
                    f"Ensure you do not use unnecessary double quotes and articulate your updated reasoning."
                )
            }

        encoded = urllib.parse.quote(clean_q)
        date_param = "%22past-24h%22" if self.current_freshness == "past-24h" else "%22past-week%22"
        url = f"https://www.linkedin.com/search/results/content/?datePosted={date_param}&keywords={encoded}&origin=GLOBAL_SEARCH_HEADER&sortBy=%5B%22date_posted%22%5D"

        self.logger.info(f"Agent executing search: '{clean_q}' | Freshness: {self.current_freshness} | Objective: {target_objective} | Rationale: {query_rationale}")
        self.driver.get(url)
        time.sleep(random.uniform(3.5, 4.5))

        body_text = self.driver.find_element(By.TAG_NAME, "body").text
        has_no_results = (
            "No results found" in body_text or
            "Try removing filters or rephrasing your search" in body_text
        )

        comment_btns = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Comment' i], button[aria-label*='comment']")
        visible_cards = len(comment_btns)
        self.cards_on_current_query = visible_cards

        if has_no_results or visible_cards == 0:
            obs = f"0 results found on LinkedIn for '{clean_q}' (Freshness: {self.current_freshness}). Page displays 'No results found'. DO NOT SCROLL on this page! Analyze why this happened and immediately execute a different query or test past-week."
            status = "zero_results"
        else:
            obs = f"Search successfully returned results for '{clean_q}' (Freshness: {self.current_freshness}). Found {visible_cards} post cards visible. Call scan_and_read_cards to inspect them."
            status = "success"

        return {
            "status": status,
            "has_no_results": has_no_results,
            "query": clean_q,
            "freshness": self.current_freshness,
            "cards_visible_count": visible_cards,
            "observation": obs
        }

    def scan_and_read_cards(self):
        try:
            self.driver.execute_script("""
                document.querySelectorAll('button[aria-label*="see more" i], .feed-shared-inline-show-more-text__see-more-less-toggle').forEach(b => { try { b.click(); } catch(_) {} });
            """)
            time.sleep(0.8)
        except Exception:
            pass

        extract_script = """
        const cards = [];
        const commentBtns = Array.from(document.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]'));

        for (let i = 0; i < commentBtns.length; i++) {
            const btn = commentBtns[i];
            let curr = btn.parentElement;
            let postCard = null;
            for (let d = 0; d < 25; d++) {
                if (!curr || curr === document.body || curr.tagName === "MAIN") break;
                const hasAuthor = !!curr.querySelector('a[href*="/in/"]');
                const innerComments = curr.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
                const text = (curr.innerText || "").trim();

                if (hasAuthor && innerComments === 1 && text.length > 35) {
                    postCard = curr;
                    if (curr.parentElement) {
                        const pComments = curr.parentElement.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
                        if (pComments > 1) break;
                    }
                } else if (innerComments > 1) {
                    break;
                }
                curr = curr.parentElement;
            }
            if (postCard && !cards.includes(postCard)) {
                cards.push(postCard);
            }
        }

        return cards.map((c, idx) => {
            const lines = (c.innerText || "").split("\\n").map(l => l.trim()).filter(l => l.length > 0);
            const nonFeed = lines.filter(l => l !== "Feed post");
            
            let authorName = nonFeed[0] || "Unknown";
            let remaining = nonFeed.slice(1);
            if (remaining.length && remaining[0].includes("•")) {
                remaining = remaining.slice(1);
            }
            let headline = remaining[0] || "";
            remaining = remaining.slice(1);
            
            let rawTime = "";
            if (remaining.length && /^(\\d+\\s*(?:s|m|min|h|hr|d|day|w|wk|mo|yr)s?|just now|yesterday)(?:\\s*•.*)?$/i.test(remaining[0])) {
                rawTime = remaining[0];
                remaining = remaining.slice(1);
            }
            if (remaining.length && /^(?:follow|\\+ follow)$/i.test(remaining[0])) {
                remaining = remaining.slice(1);
            }
            
            let content = remaining.join(" ");

            const authorEl = c.querySelector('a[href*="/in/"]');
            const authorUrl = authorEl ? authorEl.href.split("?")[0] : "";

            const isVerified = !!c.querySelector('[aria-label*="verified" i], [class*="verified"], [class*="trust-badge"]');
            const compEl = c.querySelector('a[href*="/company/"]');
            const company = compEl ? (compEl.innerText || "").split("\\n")[0].trim() : "";

            return {
                card_index: idx,
                author: authorName,
                headline: headline,
                author_url: authorUrl,
                company: company,
                is_verified: isVerified,
                raw_timestamp: rawTime,
                content: content.substring(0, 500)
            };
        });
        """

        try:
            cards = self.driver.execute_script(extract_script) or []
        except Exception as e:
            self.logger.error(f"Error extracting cards: {e}")
            cards = []

        unevaluated_cards = []
        for c in cards:
            fp = (c["author"] + "_" + c["content"][:35]).lower()
            auth_low = c["author"].strip().lower()
            url_clean = c["author_url"].strip().lower().split('?')[0].rstrip('/')

            # Exclude profiles or authors already evaluated or qualified in THIS session
            if any((ex.get("Profile URL") or "").strip().lower().split('?')[0].rstrip('/') == url_clean for ex in self.exporter.leads):
                continue
            if auth_low in self.evaluated_fingerprints or url_clean in self.evaluated_fingerprints:
                continue

            if fp not in self.evaluated_fingerprints and len(c["content"]) > 15:
                c["parsed_age_days"] = round(parse_post_age(c["raw_timestamp"]), 2)
                is_auth, auth_hint = verify_bde_lead_authenticity(c["author"], c["headline"], "", c["company"])
                c["bde_authenticity_check"] = "PASS: Direct Founder/Exec" if is_auth else f"FLAGGED: {auth_hint}"
                unevaluated_cards.append(c)

        return {
            "cards_found_count": len(unevaluated_cards),
            "cards": unevaluated_cards,
            "observation": f"Extracted {len(unevaluated_cards)} new post cards from the DOM. Read them carefully. If a candidate looks like an authentic decision-maker, call verify_profile_location to check their exact US location, or call qualify_and_save_lead."
        }

    def verify_profile_location(self, card_index: int, author_url: str):
        if not author_url or "linkedin.com/in/" not in author_url:
            return {
                "author_url": author_url,
                "exact_location": "Unknown",
                "is_usa_verified": False,
                "observation": f"Invalid or missing profile URL: {author_url}"
            }

        self.logger.info(f"Opening author profile in background tab to verify exact location: {author_url}")
        original_tab = self.driver.current_window_handle

        try:
            # Open profile in new background tab
            self.driver.switch_to.new_window("tab")
            self.driver.get(author_url)

            # 1. Wait dynamically up to 7 seconds for React hydration (check body innerText length > 500)
            for _ in range(14):
                ready = self.driver.execute_script("""
                    return !!(document.body && (document.body.innerText || '').length > 500);
                """)
                if ready:
                    time.sleep(1.0)
                    break
                time.sleep(0.5)

            extract_loc_script = """
            let location = "";
            let method = "";
            let name = "";
            let headline = "";

            // 1. Author Name (from h2 or h1)
            const h2s = Array.from(document.querySelectorAll('h2, h1')).map(h => (h.innerText || '').trim()).filter(t => t.length > 0 && !/notification|about|experience|activity|featured|ad options/i.test(t));
            if (h2s.length > 0) {
                name = h2s[0];
            }

            // 2. Primary Method: Relative proximity to 'Contact info' anchor or button
            // On modern LinkedIn profiles, location text is immediately above or adjacent to 'Contact info'
            const allEl = Array.from(document.querySelectorAll('a, button, span, div'));
            const contactEl = allEl.find(el => (el.innerText || '').trim().toLowerCase() === 'contact info');

            if (contactEl) {
                let parent = contactEl.parentElement;
                for (let d = 0; d < 6; d++) {
                    if (!parent || parent === document.body) break;
                    const lines = (parent.innerText || '').split('\\n').map(l => l.trim()).filter(l => l.length > 0 && l !== '·' && l.toLowerCase() !== 'contact info');
                    const cIdx = lines.findIndex(l => /contact info/i.test(l));
                    if (cIdx > 0 && lines[cIdx - 1].length >= 3 && lines[cIdx - 1].length <= 100) {
                        location = lines[cIdx - 1];
                        method = "contact_parent_lines";
                        break;
                    } else if (lines.length > 0 && lines[lines.length - 1].length >= 3 && lines[lines.length - 1].length <= 100) {
                        location = lines[lines.length - 1];
                        method = "contact_sibling_line";
                        break;
                    }
                    parent = parent.parentElement;
                }
            }

            // 3. Fallback 1: Parse document.body.innerText lines around 'contact info'
            if (!location) {
                const bodyLines = (document.body.innerText || '').split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                const cIdx = bodyLines.findIndex(l => l.toLowerCase() === 'contact info');
                if (cIdx > 0) {
                    for (let offset = 1; offset <= 4; offset++) {
                        const cand = bodyLines[cIdx - offset];
                        if (cand && cand !== '·' && !/followers|connections|message|follow|he\\/him|she\\/her|mutual|more/i.test(cand) && cand.length >= 3 && cand.length <= 100) {
                            location = cand;
                            method = "body_contact_offset";
                            break;
                        }
                    }
                }
            }

            // 4. Fallback 2: CSS query for top-card location classes
            if (!location) {
                const locCandidates = Array.from(document.querySelectorAll('span.text-body-small.inline.t-black--light.break-words, .pv-text-details__left-panel span.text-body-small, span[class*="location" i]'));
                for (const c of locCandidates) {
                    const raw = (c.innerText || '').trim().split('\\n')[0].replace(/•.*/, '').replace(/Contact info/i, '').trim();
                    if (raw.length >= 3 && raw.length <= 100) {
                        location = raw;
                        method = "css_selector";
                        break;
                    }
                }
            }

            // Clean location string
            if (location) {
                location = location.split('\\n')[0].replace(/·.*/, '').replace(/•.*/, '').replace(/Contact info/i, '').trim();
            }

            return {
                name: name,
                headline: headline,
                location: location,
                method: method
            };
            """
            profile_info = self.driver.execute_script(extract_loc_script) or {}
            exact_location = profile_info.get("location", "").strip()

            # Close profile tab and return to search
            self.driver.close()
            self.driver.switch_to.window(original_tab)

            # Analyze with our strict US parser
            is_usa, reason = is_verified_usa_location(exact_location)
            if is_usa:
                self.consecutive_non_usa_count = 0
                obs = f"Visited profile {author_url}. Exact top-card location: '{exact_location}'. Confirmed USA: {is_usa} ({reason})."
            else:
                self.consecutive_non_usa_count += 1
                obs = f"Visited profile {author_url}. Exact top-card location: '{exact_location}'. Confirmed USA: {is_usa} ({reason})."
                if self.consecutive_non_usa_count >= 2:
                    obs += f"\n🚨 EARLY BAILOUT ALERT: {self.consecutive_non_usa_count} consecutive cards in this search are from non-US/international locations! This feed is globally contaminated. STOP scrolling this feed immediately and execute a new search query targeting a specific US Metro (e.g. 'San Francisco', 'Austin', 'NYC') or US accelerator ('YC')."

            self.logger.info(f"Profile verification for {author_url}: Location='{exact_location}', Confirmed USA={is_usa} ({reason}, method={profile_info.get('method')})")
            print(f"      📍 Profile Top-Card Extracted: '{exact_location}' -> Confirmed USA: {is_usa} ({reason})")

            return {
                "author_url": author_url,
                "exact_location": exact_location or "Location not specified on profile top-card",
                "is_usa_verified": is_usa,
                "verification_reason": reason,
                "observation": obs
            }

        except Exception as e:
            self.logger.error(f"Error checking profile location for {author_url}: {e}")
            try:
                self.driver.close()
                self.driver.switch_to.window(original_tab)
            except Exception:
                pass
            return {
                "author_url": author_url,
                "exact_location": "Error inspecting profile",
                "is_usa_verified": False,
                "observation": f"Could not verify profile location due to: {e}"
            }

    def propose_code_improvement(self, file_path: str, target_code: str, replacement_code: str, explanation: str, expected_benefit: str):
        print("\n" + "=" * 80)
        print(f"{Style.YELLOW}{Style.BOLD}🛠️ AGENT SELF-IMPROVEMENT PROPOSAL (User Permission Required){Style.RESET}")
        print(f"📁 Target File: {Style.CYAN}{file_path}{Style.RESET}")
        print(f"📖 Detailed Explanation: {explanation}")
        print(f"🚀 Expected Benefit: {expected_benefit}")
        print("-" * 80)
        print(f"{Style.RED}--- TARGET CODE TO BE REPLACED ---{Style.RESET}")
        print(target_code[:400] + ("..." if len(target_code) > 400 else ""))
        print(f"{Style.GREEN}+++ REPLACEMENT CODE TO BE INSERTED ---{Style.RESET}")
        print(replacement_code[:400] + ("..." if len(replacement_code) > 400 else ""))
        print("=" * 80)

        try:
            user_perm = input(f"{Style.CYAN}Do you approve applying this code improvement? (y/n, default: y): {Style.RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            user_perm = "n"

        if user_perm not in ["y", "yes", ""]:
            self.logger.info("User declined agent's proposed code modification.")
            return {
                "status": "declined",
                "observation": "User declined the proposed code modification. Continue using existing tools."
            }

        # Resolve path safely
        resolved_path = file_path
        if not os.path.isabs(resolved_path):
            candidate = os.path.join(BASE_DIR, resolved_path)
            if os.path.exists(candidate):
                resolved_path = candidate

        # Apply change safely with backup & compilation verification
        if not os.path.exists(resolved_path):
            return {
                "status": "error",
                "observation": f"File '{file_path}' does not exist on disk."
            }

        backup_path = f"{resolved_path}.bak"
        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                content = f.read()

            if target_code not in content:
                return {
                    "status": "error",
                    "observation": f"Target code snippet was not found in {file_path}. Ensure exact matching whitespace and indentation."
                }

            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(content)

            new_content = content.replace(target_code, replacement_code, 1)
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            try:
                py_compile.compile(resolved_path, doraise=True)
            except Exception as comp_err:
                with open(backup_path, "r", encoding="utf-8") as f:
                    f.write(content)
                self.logger.error(f"Syntax error compiling modified code: {comp_err}")
                return {
                    "status": "syntax_error",
                    "observation": f"Code modification caused a syntax error ({comp_err}). Successfully rolled back to backup."
                }

            self.logger.info(f"Agent successfully updated {file_path}. Benefit: {expected_benefit}")
            print(f"{Style.GREEN}✅ Code improvement successfully verified and applied to {file_path}!{Style.RESET}\n")
            return {
                "status": "applied_successfully",
                "observation": f"Code improvement successfully verified and applied to {file_path}. The tool/logic is now upgraded."
            }

        except Exception as e:
            self.logger.error(f"Error applying code modification: {e}")
            return {
                "status": "error",
                "observation": f"Failed to apply modification due to: {e}"
            }

    def ask_developer(self, question: str, context: str = ""):
        print("\n" + "=" * 80)
        print(f"{Style.YELLOW}{Style.BOLD}🤖 AGENT ASKING DEVELOPER FOR GUIDANCE{Style.RESET}")
        if context:
            print(f"📌 Context: {context}")
        print(f"❓ Question from Agent: {Style.BOLD}{question}{Style.RESET}")
        print("=" * 80)

        try:
            answer = input(f"{Style.CYAN}Enter your advice/instruction for the agent: {Style.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""

        if not answer:
            answer = "Proceed using your best judgment based on memory and guidelines."

        self.logger.info(f"Agent asked developer: '{question}' | Developer responded: '{answer}'")
        print(f"{Style.GREEN}✓ Guidance delivered to agent.{Style.RESET}\n")

        return {
            "status": "guidance_received",
            "developer_guidance": answer,
            "observation": f"Developer response: '{answer}'. Follow this instruction."
        }

    def scroll_feed(self, steps: int = 1, rationale: str = ""):
        self.scroll_count_on_query += steps
        self.logger.info(f"Agent scrolling down feed: {steps} steps | Rationale: {rationale}")

        for _ in range(steps):
            scroll_pixels = random.randint(650, 950)
            self.driver.execute_script(f"window.scrollBy({{ top: {scroll_pixels}, behavior: 'smooth' }});")
            time.sleep(random.uniform(2.0, 3.0))
            if random.random() < 0.25:
                self.driver.execute_script("window.scrollBy({ top: -120, behavior: 'smooth' });")
                time.sleep(0.5)

        comment_btns = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Comment' i], button[aria-label*='comment']")
        total_cards = len(comment_btns)
        self.cards_on_current_query = total_cards

        body_text = self.driver.find_element(By.TAG_NAME, "body").text
        at_end = "No more results" in body_text or "You've viewed all" in body_text

        if self.consecutive_non_usa_count >= 2:
            return {
                "total_cards_in_dom": total_cards,
                "scroll_count": self.scroll_count_on_query,
                "at_end_of_feed": at_end,
                "observation": f"🚨 FEED BAILOUT TRIGGERED: Feed has {self.consecutive_non_usa_count} consecutive international non-US cards! Scrolling further on this query is unproductive. Immediately execute a new search query anchored with a US Tech Hub (e.g. 'San Francisco', 'Austin', 'NYC') or US Accelerator ('YC')."
            }

        return {
            "total_cards_in_dom": total_cards,
            "scroll_count": self.scroll_count_on_query,
            "at_end_of_feed": at_end,
            "observation": f"Scrolled {steps} step(s). Total cards in DOM: {total_cards}. Call scan_and_read_cards to inspect the newly loaded cards."
        }

    def qualify_and_save_lead(self, card_index: int, author: str, profile_url: str, headline: str, role: str, company: str, location: str, fit_score: int, custom_pitch: str, reasoning: str):
        # Strict Authenticity Guardrail: Disqualify VCs, media, curators, recruiters, and non-founders
        is_authentic, auth_reason = verify_bde_lead_authenticity(author=author, headline=headline, role=role, company=company)
        if not is_authentic:
            self.logger.warning(f"Rejected lead qualification for {author}: {auth_reason}")
            print(f"      ⚠️ Disqualified Lead Candidate: '{author}' — Reason: {auth_reason}")
            return {
                "status": "lead_disqualified",
                "author": author,
                "rejection_reason": auth_reason,
                "observation": f"Disqualified lead candidate '{author}'. Reason: {auth_reason}. Lead MUST be an authentic direct Founder, Co-Founder, CEO, CTO, or VP of Engineering of their own software/AI startup (like Billy Jeremijenko), NOT a VC, accelerator, scout, or media page. Call skip_card or inspect next card."
            }

        post_url = ""

        # Step 1: Setup in-page clipboard hook before clicking
        try:
            self.driver.execute_script("""
                window.__bdeCaptured = null;
                if (navigator.clipboard) {
                    const origWrite = navigator.clipboard.writeText;
                    navigator.clipboard.writeText = function(text) {
                        window.__bdeCaptured = text;
                        if (origWrite) return origWrite.apply(navigator.clipboard, arguments);
                        return Promise.resolve();
                    };
                }
            """)

            # Step 2: Precisely target the 3-dots button INSIDE the specific post card (avoiding page filter dropdowns)
            click_dots_js = f"""
            const commentBtns = Array.from(document.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]'));
            if ({card_index} >= commentBtns.length) return false;
            let curr = commentBtns[{card_index}].parentElement;
            let postCard = null;
            for (let d = 0; d < 25; d++) {{
                if (!curr || curr === document.body || curr.tagName === "MAIN") break;
                const hasAuthor = !!curr.querySelector('a[href*="/in/"]');
                const innerComments = curr.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
                if (hasAuthor && innerComments === 1) {{
                    postCard = curr;
                    if (curr.parentElement && curr.parentElement.querySelectorAll('button[aria-label*="Comment" i]').length > 1) break;
                }} else if (innerComments > 1) break;
                curr = curr.parentElement;
            }}
            if (!postCard) return false;

            const dotsBtn = postCard.querySelector(
                'button[aria-label*="control menu" i], ' +
                'button[aria-label*="More actions" i], ' +
                'button[aria-label*="options" i], ' +
                'button.feed-shared-control-menu__trigger, ' +
                '.feed-shared-control-menu button'
            );
            if (!dotsBtn) return false;
            dotsBtn.scrollIntoView({{ block: "nearest" }});
            dotsBtn.click();
            return true;
            """
            clicked_dots = self.driver.execute_script(click_dots_js)
            if clicked_dots:
                time.sleep(1.0)
                # Click [data-view-name="feed-control-menu-copy-link"] or "Copy link to post"
                click_copy_js = """
                const copyBtn = document.querySelector('[data-view-name="feed-control-menu-copy-link"]');
                if (copyBtn) {
                    copyBtn.click();
                    return true;
                }
                const items = Array.from(document.querySelectorAll('[role="menuitem"], div.artdeco-dropdown__item, button, span, li'));
                for (const it of items) {
                    const txt = (it.innerText || "").trim().toLowerCase();
                    if (txt.includes("copy link to post") || txt === "copy link") {
                        it.click();
                        return true;
                    }
                }
                return false;
                """
                self.driver.execute_script(click_copy_js)
                time.sleep(1.0)

                captured = self.driver.execute_script("return window.__bdeCaptured || null;")
                if captured and ("lnkd.in" in captured or "linkedin.com" in captured):
                    post_url = captured.strip()

                # Close dropdown
                self.driver.execute_script("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));")
        except Exception as e:
            self.logger.error(f"Error capturing post URL via 3-dots: {e}")

        # Step 3: If 3-dots clipboard didn't capture, inspect postCard element for direct post anchor or activity URN
        if not post_url:
            try:
                card_fallback_info = self.driver.execute_script(f"""
                    const commentBtns = Array.from(document.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]'));
                    if ({card_index} >= commentBtns.length) return null;
                    let curr = commentBtns[{card_index}].parentElement;
                    for (let d = 0; d < 25; d++) {{
                        if (!curr || curr === document.body) break;
                        const a = curr.querySelector('a[href*="/feed/update/urn:li:"], a[href*="/posts/"]');
                        if (a) return {{ directUrl: a.href.split('?')[0] }};
                        const urn = curr.getAttribute('data-urn') || curr.getAttribute('data-activity-urn') || curr.getAttribute('data-id');
                        if (urn && urn.includes('urn:li:activity:')) return {{ activityUrn: urn }};
                        curr = curr.parentElement;
                    }}
                    return null;
                """)
                if card_fallback_info:
                    if card_fallback_info.get("directUrl"):
                        post_url = card_fallback_info["directUrl"]
                    elif card_fallback_info.get("activityUrn"):
                        urn = card_fallback_info["activityUrn"]
                        post_url = f"https://www.linkedin.com/feed/update/{urn}/"
            except Exception as e:
                self.logger.error(f"Fallback post URL extraction error: {e}")

        # If still empty, record specific unknown update rather than broad activity fallback
        if not post_url:
            post_url = "https://www.linkedin.com/feed/update/urn:li:activity:unknown"

        # Ensure Profile URL is valid
        clean_profile_url = profile_url.strip() if profile_url else ""

        # Lead record with exact requested CSV columns
        lead_record = {
            "Profile URL": clean_profile_url,
            "Post URL": post_url,
            "Fit Score": fit_score,
            "Author Name": author,
            "Title / Headline": headline,
            "Verified Location": location,
            "Company Name": company,
            "Custom Outreach Hook": custom_pitch,
            "Reasoning": reasoning
        }

        self.exporter.append_lead(lead_record)
        self.memory.record_qualified_lead(lead_record)
        self.qualified_on_current_query += 1
        total_leads = len(self.exporter.leads)

        # Mark fingerprint and profile as evaluated to prevent duplicates
        self.evaluated_fingerprints.add((author + "_" + reasoning[:30]).lower())
        if author:
            self.evaluated_fingerprints.add(author.strip().lower())
        if clean_profile_url:
            self.evaluated_fingerprints.add(clean_profile_url.strip().lower().split('?')[0].rstrip('/'))

        log_qualified(f"[{total_leads}] {author} | {role} @ {company} | Score: {fit_score}/100")
        print(f"      🔗 Profile URL: {clean_profile_url}")
        print(f"      📌 Authentic Post URL: {post_url}")
        print(f"      📍 Location: {location}")
        print(f"      💡 Custom Pitch Hook: {Style.BOLD}{custom_pitch}{Style.RESET}")

        return {
            "status": "lead_saved_successfully",
            "author": author,
            "profile_url": clean_profile_url,
            "post_url": post_url,
            "fit_score": fit_score,
            "total_qualified_leads_collected": total_leads,
            "observation": f"Successfully qualified and saved lead #{total_leads} ({author}). Specific post URL captured: {post_url}."
        }

    def skip_card(self, card_index: int, author: str, rejection_reason: str):
        self.skipped_count += 1
        self.evaluated_fingerprints.add((author + "_" + rejection_reason[:25]).lower())
        log_skipped(f"Card #{card_index} ({author}) — Reason: {rejection_reason}")
        return {
            "status": "card_skipped",
            "author": author,
            "reason": rejection_reason,
            "observation": f"Skipped card #{card_index} ({author}). Reason: {rejection_reason}."
        }

    def search_web(self, query: str, rationale: str = ""):
        self.logger.info(f"Agent web search: '{query}' | Rationale: {rationale}")
        results = search_web_api(query)
        return {
            "query": query,
            "rationale": rationale,
            "results": results,
            "observation": f"Web search for '{query}' returned {len(results)} snippets."
        }

