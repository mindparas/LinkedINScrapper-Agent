import os
import sys
import time
import json
import re

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("Please install selenium and webdriver-manager:")
    print("pip install selenium webdriver-manager")
    sys.exit(1)

def main():
    print("=" * 60)
    print(" LinkedIn Live Post URL Discovery Tool (Selenium)")
    print("=" * 60)

    options = Options()
    # Use normal UI mode so the user can interact
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Allow clipboard access
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.clipboard": 1
    })

    print("\n[1/4] Launching Google Chrome browser...")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"Direct Chrome launch failed ({e}), trying default Chrome...")
        driver = webdriver.Chrome(options=options)

    try:
        print("\n[2/4] Navigating to LinkedIn Login...")
        driver.get("https://www.linkedin.com/login")

        print("\n" + "*" * 60)
        print("👉 ACTION REQUIRED IN THE CHROME WINDOW:")
        print("1. Log in to your LinkedIn account in the browser.")
        print("2. Once logged in, DO NOT close the browser.")
        print("*" * 60)
        input("\nPress ENTER here in the terminal once you have logged in...")

        search_query = "hiring founding engineer"
        encoded_query = "hiring%20founding%20engineer%20(%22United%20States%22%20OR%20%22US%20remote%22%20OR%20%22remote%20US%22)"
        search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&origin=GLOBAL_SEARCH_HEADER&sortBy=%5B%22relevance%22%5D"

        print(f"\n[3/4] Navigating to Search Results:\n{search_url}")
        driver.get(search_url)
        time.sleep(5)

        print("\n[4/4] Analyzing Post Cards in the DOM...")

        # Run in-page diagnostic script
        analysis_script = """
        const results = [];
        const commentBtns = Array.from(document.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]'));
        
        for (let i = 0; i < Math.min(commentBtns.length, 5); i++) {
            const btn = commentBtns[i];
            let curr = btn.parentElement;
            let card = null;

            for (let d = 0; d < 25; d++) {
                if (!curr || curr === document.body || curr.tagName === 'MAIN') break;
                const hasAuthor = !!curr.querySelector('a[href*="/in/"]');
                const comments = curr.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
                const text = (curr.innerText || '').trim();

                if (hasAuthor && comments === 1 && text.length > 40) {
                    card = curr;
                    if (curr.parentElement) {
                        const parentComments = curr.parentElement.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
                        if (parentComments > 1) break;
                    }
                } else if (comments > 1) {
                    break;
                }
                curr = curr.parentElement;
            }

            if (!card) continue;

            const authorEl = card.querySelector('a[href*="/in/"]');
            const author = (authorEl ? (authorEl.innerText || '') : '').split('\\n')[0].replace(/•.*$/, '').trim();
            const authorUrl = authorEl ? authorEl.href.split('?')[0] : '';

            // Find all anchor links
            const allLinks = Array.from(card.querySelectorAll('a[href]')).map(a => a.href);

            // Find 3-dots control menu button
            const threeDotsBtn = card.querySelector('button[aria-label*="control menu" i], button[aria-label*="options" i], button[aria-label*="More" i], button.feed-shared-control-menu__trigger, button.artdeco-dropdown__trigger');
            
            // Gather all attributes from all elements inside card
            const attrList = [];
            const allElements = [card, ...card.querySelectorAll('*')];
            allElements.forEach(el => {
                if (el.attributes) {
                    for (let a = 0; a < el.attributes.length; a++) {
                        const name = el.attributes[a].name;
                        const val = el.attributes[a].value;
                        if (val && (val.includes('activity') || val.includes('urn:li:') || val.includes('feed/update') || val.includes('posts/') || /[0-9]{16,22}/.test(val))) {
                            attrList.push({ tag: el.tagName, attr: name, value: val.slice(0, 150) });
                        }
                    }
                }
            });

            results.push({
                cardIndex: i + 1,
                author,
                authorUrl,
                cardHeight: Math.round(card.getBoundingClientRect().height),
                links: allLinks.filter(l => !l.includes('/in/')),
                matchingAttrs: attrList.slice(0, 10),
                hasThreeDots: !!threeDotsBtn,
                threeDotsAria: threeDotsBtn ? threeDotsBtn.getAttribute('aria-label') : null,
                htmlSnippet: card.outerHTML.slice(0, 500)
            });
        }
        return results;
        """

        cards_data = driver.execute_script(analysis_script)
        print(f"\nFound {len(cards_data)} analyzed post cards:")
        print(json.dumps(cards_data, indent=2))

        # Now let's test clicking the 3-dots button and checking what happens!
        print("\n" + "=" * 60)
        print("Testing 'Copy Link to Post' via the 3-dots menu on Card #1...")
        print("=" * 60)

        # 1. Click 3-dots button using JavaScript
        click_three_dots = """
        const threeDots = document.querySelector('button[aria-label*="control menu for post" i], button[aria-label*="control menu" i]');
        if (threeDots) {
            threeDots.click();
            return { clicked: true, aria: threeDots.getAttribute('aria-label') };
        }
        return { clicked: false, error: "Three dots button not found" };
        """
        click_res = driver.execute_script(click_three_dots)
        print("Three dots click:", click_res)

        # Wait for menu to render
        time.sleep(2)

        # 2. Inspect the opened dropdown menu items
        inspect_menu = """
        const items = [];
        const allClickables = Array.from(document.querySelectorAll('div[role="button"], button, li, a, span'));
        allClickables.forEach(el => {
            const txt = (el.innerText || '').trim();
            const aria = el.getAttribute('aria-label') || '';
            if (txt.includes('Copy') || txt.includes('link') || aria.includes('Copy') || aria.includes('link') || txt.includes('Save') || txt.includes('Embed')) {
                items.push({
                    tag: el.tagName,
                    text: txt.slice(0, 80),
                    aria: aria,
                    className: (el.className || '').slice(0, 60),
                    href: el.getAttribute('href') || null,
                    dataAttrs: Object.fromEntries(Array.from(el.attributes).filter(a => a.name.startsWith('data-')).map(a => [a.name, a.value.slice(0, 100)]))
                });
            }
        });
        return items;
        """
        menu_items = driver.execute_script(inspect_menu)
        print("\nMenu items found in dropdown:")
        print(json.dumps(menu_items, indent=2))

        # 3. Click "Copy link to post" and read clipboard
        click_copy_link = """
        const allEls = Array.from(document.querySelectorAll('div[role="button"], button, li, span, p'));
        for (const el of allEls) {
            const txt = (el.innerText || '').trim();
            if (/^Copy link to post$/i.test(txt) || txt.includes('Copy link to post') || txt.includes('Copy link')) {
                el.click();
                return { clickedCopyLink: true, elementText: txt };
            }
        }
        return { clickedCopyLink: false, error: "Copy link element not found" };
        """
        copy_res = driver.execute_script(click_copy_link)
        print("\nCopy link click result:", copy_res)
        time.sleep(1)

        # Try to read clipboard via JavaScript
        clipboard_text = driver.execute_script("""
            try {
                // Return dummy or check if navigator.clipboard is available
                return window.__copiedLink || "Check system clipboard";
            } catch (_) {
                return null;
            }
        """)
        print("\nClipboard text:", clipboard_text)

        # Save HTML dump of first card to disk
        card_html = driver.execute_script("""
            const postCard = document.querySelector('[componentkey*="update-card"], [role="listitem"]');
            if (postCard) return postCard.outerHTML;
            const threeDots = document.querySelector('button[aria-label*="control menu for post" i]');
            if (threeDots) {
                let curr = threeDots;
                for (let i = 0; i < 15; i++) {
                    if (!curr || curr === document.body) break;
                    if (curr.getAttribute('role') === 'listitem' || (curr.className && curr.className.includes('feed-shared-update'))) return curr.outerHTML;
                    curr = curr.parentElement;
                }
                return threeDots.parentElement.parentElement.parentElement.outerHTML;
            }
            return document.body.innerHTML.slice(0, 20000);
        """)

        tools_dir = os.path.dirname(os.path.abspath(__file__))
        debug_dir = os.path.join(os.path.dirname(tools_dir), "debug")
        os.makedirs(debug_dir, exist_ok=True)

        dump_path = os.path.join(debug_dir, "debug_card_dump.html")
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(card_html)
        print(f"\n✅ Saved complete HTML dump to '{dump_path}'!")

        print("\n" + "=" * 60)
        print("NOW PASTE WHAT IS IN YOUR CLIPBOARD (Ctrl+V) RIGHT HERE:")
        print("=" * 60)
        pasted = input("Pasted link: ")
        print(f"\n🎉 EXCELLENT! Pasted link is: {pasted}\n")

        copied_path = os.path.join(debug_dir, "copied_post_url.txt")
        with open(copied_path, "w", encoding="utf-8") as f:
            f.write(pasted + "\n")

    finally:
        driver.quit()
        print("Browser closed.")

if __name__ == "__main__":
    main()
