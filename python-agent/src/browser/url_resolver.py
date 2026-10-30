"""
Bulletproof Tiered Post URL Resolver for LinkedIn.
Captures authentic, clickable 'https://lnkd.in/...' shortlinks directly from
the search result card or author's activity feed using native ActionChains.
"""

import time
import re
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

CLIPBOARD_HOOK_SCRIPT = """
window.__bdeCapturedUrl = null;
window.__bdeClipboardCalls = [];

if (navigator.clipboard) {
    const origWrite = navigator.clipboard.writeText;
    navigator.clipboard.writeText = async function(text) {
        window.__bdeCapturedUrl = text;
        window.__bdeClipboardCalls.push({ type: 'writeText', val: text });
        if (origWrite) {
            try { return await origWrite.apply(navigator.clipboard, arguments); } catch(_) {}
        }
        return Promise.resolve();
    };
}

if (document.execCommand) {
    const origExec = document.execCommand;
    document.execCommand = function(cmd) {
        if (cmd === 'copy') {
            const sel = window.getSelection ? window.getSelection().toString() : '';
            if (sel && (sel.includes('lnkd.in') || sel.includes('linkedin.com'))) {
                window.__bdeCapturedUrl = sel;
            }
        }
        return origExec.apply(this, arguments);
    };
}
"""

def extract_author_handle(author_url: str) -> str:
    if not author_url:
        return ""
    parts = author_url.split('/in/')
    return parts[1].replace('/', '').split('?')[0].strip() if len(parts) > 1 else ""

def click_dot_and_copy(driver, container_element, logger=None) -> str:
    """
    Given a post card container element, clicks its 3-dots button and clicks 'Copy link to post'
    using ActionChains to ensure React synthetic events fire correctly.
    """
    try:
        # Install in-page clipboard hook
        driver.execute_script(CLIPBOARD_HOOK_SCRIPT)
        
        # 1. Locate 3-dots control menu button within the post container
        dot_btn = container_element.find_element(
            By.CSS_SELECTOR,
            'button[aria-label*="control menu" i], button[aria-label*="More actions" i], button[aria-label*="options" i]'
        )
        
        # Scroll container and dot button into center view
        driver.execute_script("arguments[0].scrollIntoView({ block: 'center', behavior: 'instant' });", dot_btn)
        time.sleep(0.5)
        
        # Physical hover and click via ActionChains
        actions = ActionChains(driver)
        actions.move_to_element(dot_btn).pause(0.3).click().perform()
        time.sleep(1.2)
        
        # 2. Locate 'Copy link to post' in the rendered dropdown
        copy_el = driver.execute_script("""
            const candidates = Array.from(document.querySelectorAll('*')).filter(el => {
                const t = (el.innerText || '').trim();
                return t === 'Copy link to post' || t === 'Copy link' || t.includes('Copy link to post');
            });
            if (candidates.length === 0) return null;
            return candidates[candidates.length - 1];
        """)
        
        if copy_el:
            actions = ActionChains(driver)
            actions.move_to_element(copy_el).pause(0.3).click().perform()
            time.sleep(1.2)
        else:
            # Fallback JavaScript dispatch
            driver.execute_script("""
                const candidates = Array.from(document.querySelectorAll('*')).filter(el => {
                    const t = (el.innerText || '').trim();
                    return t === 'Copy link to post' || t === 'Copy link';
                });
                if (candidates.length > 0) {
                    const target = candidates[candidates.length - 1];
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                    target.click();
                }
            """)
            time.sleep(1.2)
            
        # 3. Retrieve captured URL from hook
        captured = driver.execute_script("return window.__bdeCapturedUrl;")
        
        # Close any open dropdown cleanly
        driver.execute_script("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));")
        
        if captured and ("lnkd.in/" in captured or "linkedin.com/" in captured):
            return captured.strip()
            
    except Exception as e:
        if logger:
            logger.warning(f"click_dot_and_copy encountered error: {e}")
        try:
            driver.execute_script("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));")
        except Exception:
            pass
            
    return ""

def resolve_post_url(driver, card_id: str, author_url: str, post_content_snippet: str = "", direct_post_url: str = "", logger=None) -> str:
    """
    3-Tier Post URL Resolution Engine:
    Tier 0: Direct permalink already present in DOM
    Tier 1: Card 3-dots control menu on search results page via ActionChains
    Tier 2: Direct DOM / URN / Toast inspect
    Tier 3: Author profile recent-activity feed inspection via ActionChains 3-dots
    """
    # ── Tier 0: Direct URL already present ────────────────────────────────────
    if direct_post_url and ("linkedin.com/feed/update/" in direct_post_url or "linkedin.com/posts/" in direct_post_url or "lnkd.in/" in direct_post_url):
        if logger:
            logger.info(f"Tier 0 match: direct post URL already present: {direct_post_url}")
        return direct_post_url.strip()

    # ── Tier 1: ActionChains on Search Results Card ───────────────────────────
    handle = extract_author_handle(author_url)
    try:
        # Locate target card in search DOM by unique card_id or author link
        target_card = driver.execute_script("""
            return (function(cardId, handle) {
                if (cardId) {
                    const c = document.querySelector(`[data-bde-card-id="${cardId}"]`);
                    if (c) return c;
                }
                if (handle) {
                    const a = document.querySelector(`a[href*="/in/${handle}"]`);
                    if (a) {
                        let curr = a;
                        for (let d = 0; d < 20; d++) {
                            if (!curr || curr === document.body) break;
                            if (curr.getAttribute('role') === 'listitem' || curr.classList.contains('feed-shared-update-v2')) {
                                return curr;
                            }
                            curr = curr.parentElement;
                        }
                    }
                }
                return null;
            })(arguments[0], arguments[1]);
        """, card_id, handle)
        
        if target_card:
            captured_url = click_dot_and_copy(driver, target_card, logger)
            if captured_url and "lnkd.in/" in captured_url:
                if logger:
                    logger.info(f"Tier 1 match: captured authentic post shortlink via search card 3-dots: {captured_url}")
                return captured_url
    except Exception as e:
        if logger:
            logger.warning(f"Tier 1 search card capture error: {e}")

    # ── Tier 2: Card DOM attribute inspection ────────────────────────────────
    try:
        dom_url = driver.execute_script("""
            return (function(cardId) {
                const card = cardId ? document.querySelector(`[data-bde-card-id="${cardId}"]`) : null;
                if (!card) return null;
                const a = card.querySelector('a[href*="/feed/update/urn:li:"], a[href*="/posts/"], a.update-components-actor__sub-description-link');
                if (a && a.href) return a.href.split('?')[0];
                const urn = card.getAttribute('data-urn') || card.getAttribute('data-activity-urn') || card.getAttribute('data-id');
                if (urn && urn.includes('urn:li:')) return `https://www.linkedin.com/feed/update/${urn}/`;
                return null;
            })(arguments[0]);
        """, card_id)
        if dom_url and "unknown" not in dom_url:
            if logger:
                logger.info(f"Tier 2 match: resolved post URL from DOM: {dom_url}")
            return dom_url.strip()
    except Exception as e:
        if logger:
            logger.warning(f"Tier 2 DOM inspection error: {e}")

    # ── Tier 3: Author Activity Feed Permamatch via ActionChains 3-Dots ───────
    if author_url and "linkedin.com/in/" in author_url:
        orig_tab = driver.current_window_handle
        try:
            clean_author_url = author_url.split('?')[0].rstrip('/')
            activity_url = f"{clean_author_url}/recent-activity/all/"
            if logger:
                logger.info(f"Tier 3: navigating to author activity feed to capture authentic post shortlink: {activity_url}")
            
            driver.switch_to.new_window("tab")
            driver.get(activity_url)
            time.sleep(5.0)

            # Match first 40 chars of snippet against activity posts
            snippet_clean = re.sub(r'[^a-zA-Z0-9\s]', '', (post_content_snippet or "")[:50]).lower().strip()
            
            # Locate target post container in activity feed
            matched_post = driver.execute_script("""
                return (function(targetSnippet) {
                    const items = Array.from(document.querySelectorAll('.feed-shared-update-v2, div[role="listitem"]'));
                    
                    for (const item of items) {
                        const text = (item.innerText || '').toLowerCase().replace(/[^a-zA-Z0-9\\s]/g, '');
                        const hasDot = !!item.querySelector('button[aria-label*="control menu" i]');
                        if (hasDot && targetSnippet && text.includes(targetSnippet)) {
                            return item;
                        }
                    }
                    // Fallback to top post with dot button
                    for (const item of items) {
                        if (item.querySelector('button[aria-label*="control menu" i]')) {
                            return item;
                        }
                    }
                    return null;
                })(arguments[0]);
            """, snippet_clean)

            if matched_post:
                activity_captured = click_dot_and_copy(driver, matched_post, logger)
                driver.close()
                driver.switch_to.window(orig_tab)
                if activity_captured and ("lnkd.in/" in activity_captured or "linkedin.com/" in activity_captured):
                    if logger:
                        logger.info(f"Tier 3 match: successfully captured authentic post shortlink via activity feed 3-dots: {activity_captured}")
                    return activity_captured
            else:
                driver.close()
                driver.switch_to.window(orig_tab)

        except Exception as e:
            if logger:
                logger.error(f"Tier 3 activity feed inspection failed: {e}")
            try:
                driver.close()
                driver.switch_to.window(orig_tab)
            except Exception:
                pass

    # Safe fallback: author activity URL rather than broken string
    clean_handle = author_url.split('?')[0].rstrip('/')
    return f"{clean_handle}/recent-activity/all/"
