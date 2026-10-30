"""
Deterministic DOM Card Scanner for LinkedIn Content Feeds.
Identifies post cards, tags each uniquely in the DOM, and extracts rich candidate data.
"""

import time
from typing import List, Dict, Any

DOM_SCAN_SCRIPT = """
return (function() {
    // 1. Expand all 'see more' buttons across the feed
    document.querySelectorAll('button[aria-label*="see more" i], .feed-shared-inline-show-more-text__see-more-less-toggle').forEach(b => {
        try { b.click(); } catch (_) {}
    });

    const cards = [];
    // Strategy A: Find all listitems that look like search result update cards
    const listItems = Array.from(document.querySelectorAll('div[role="listitem"]'));
    for (const item of listItems) {
        const hasAuthor = !!item.querySelector('a[href*="/in/"]');
        const hasCommentsOrActions = !!item.querySelector('button[aria-label*="Comment" i], button[aria-label*="comment"], button[aria-label*="control menu" i]');
        const text = (item.innerText || '').trim();
        if (hasAuthor && hasCommentsOrActions && text.length > 40) {
            cards.push(item);
        }
    }

    // Strategy B fallback: Find cards from comment buttons upwards
    if (cards.length === 0) {
        const commentBtns = Array.from(document.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]'));
        for (const btn of commentBtns) {
            let curr = btn.parentElement;
            let postCard = null;
            for (let d = 0; d < 25; d++) {
                if (!curr || curr === document.body || curr.tagName === "MAIN") break;
                const hasAuthor = !!curr.querySelector('a[href*="/in/"]');
                const innerComments = curr.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
                const text = (curr.innerText || "").trim();
                if (hasAuthor && innerComments === 1 && text.length > 40) {
                    postCard = curr;
                    if (curr.parentElement && curr.parentElement.querySelectorAll('button[aria-label*="Comment" i]').length > 1) break;
                } else if (innerComments > 1) {
                    break;
                }
                curr = curr.parentElement;
            }
            if (postCard && !cards.includes(postCard)) {
                cards.push(postCard);
            }
        }
    }

    return cards.map((c, idx) => {
        // Tag card with deterministic unique ID if not already tagged
        let cardId = c.getAttribute('data-bde-card-id');
        if (!cardId) {
            cardId = 'bde_card_' + idx + '_' + Math.random().toString(36).substring(2, 8);
            c.setAttribute('data-bde-card-id', cardId);
        }

        // Author Link & Profile URL
        const authorEl = c.querySelector('a[href*="/in/"]');
        let authorUrl = "";
        let authorName = "";
        if (authorEl) {
            authorUrl = authorEl.href.split('?')[0].replace(/\\/$/, '');
            // Check for explicit author name inside author anchor or bold spans
            const nameEl = authorEl.querySelector('p span, span[dir="ltr"], .update-components-actor__name');
            if (nameEl) {
                authorName = (nameEl.innerText || '').trim();
            }
        }

        // Parse lines for headline and timestamp
        const lines = (c.innerText || '').split('\\n').map(l => l.trim()).filter(l => l.length > 0 && l !== 'Feed post');
        
        if (!authorName && lines.length > 0) {
            authorName = lines[0].replace(/•.*/, '').trim();
        }

        let remaining = lines.filter(l => l !== authorName && !l.startsWith('•') && l.toLowerCase() !== 'follow' && l.toLowerCase() !== '+ follow');
        
        let headline = "";
        if (remaining.length > 0) {
            // First substantial remaining line is usually the headline
            headline = remaining[0];
            remaining = remaining.slice(1);
        }

        let rawTime = "";
        if (remaining.length > 0 && /^(\\d+\\s*(?:s|m|min|h|hr|d|day|w|wk|mo|yr)s?|just now|yesterday)(?:\\s*•.*)?$/i.test(remaining[0])) {
            rawTime = remaining[0];
            remaining = remaining.slice(1);
        } else {
            // Look for time pattern anywhere in first 5 lines
            for (let i = 0; i < Math.min(5, remaining.length); i++) {
                if (/^(\\d+\\s*(?:s|m|min|h|hr|d|day|w|wk|mo|yr)s?|just now|yesterday)/i.test(remaining[i])) {
                    rawTime = remaining[i];
                    break;
                }
            }
        }

        // Full post content text
        const content = remaining.join(' ');

        // Check if 3-dots control button exists in this card
        const dotBtn = c.querySelector('button[aria-label*="control menu" i], button[aria-label*="More actions" i], button[aria-label*="options" i]');
        const hasDot = !!dotBtn;
        const dotAria = dotBtn ? dotBtn.getAttribute('aria-label') : '';

        // Extract direct post link / URN if already present in DOM
        let directUrl = "";
        const postAnchor = c.querySelector('a[href*="/feed/update/urn:li:"], a[href*="/posts/"], a.update-components-actor__sub-description-link');
        if (postAnchor && postAnchor.href) {
            directUrl = postAnchor.href.split('?')[0];
        } else {
            const dataUrn = c.getAttribute('data-urn') || c.getAttribute('data-activity-urn') || c.getAttribute('data-id');
            if (dataUrn && dataUrn.includes('urn:li:')) {
                directUrl = `https://www.linkedin.com/feed/update/${dataUrn}/`;
            }
        }

        // Tagged company
        const compEl = c.querySelector('a[href*="/company/"]');
        const company = compEl ? (compEl.innerText || '').split('\\n')[0].trim() : '';

        return {
            card_id: cardId,
            author: authorName,
            headline: headline,
            author_url: authorUrl,
            company: company,
            raw_timestamp: rawTime,
            direct_post_url: directUrl,
            has_dot_button: hasDot,
            dot_aria_label: dotAria,
            content: content.substring(0, 1500)
        };
    });
})();
"""

def scan_linkedin_content_cards(driver, logger=None) -> List[Dict[str, Any]]:
    """
    Executes DOM scanning script and returns structured card objects with unique card IDs.
    """
    try:
        cards = driver.execute_script(DOM_SCAN_SCRIPT) or []
        if logger:
            logger.info(f"DOM scanner extracted {len(cards)} raw cards from page.")
        return cards
    except Exception as e:
        if logger:
            logger.error(f"DOM scanner failed: {e}")
        return []

