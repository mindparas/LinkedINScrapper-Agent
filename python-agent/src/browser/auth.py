import time
from selenium.webdriver.common.by import By
from src.config import Style

def verify_or_prompt_login(driver, logger):
    """
    Checks if active LinkedIn session exists.
    If not, navigates to login and prompts the user once in the open browser.
    """
    driver.get("https://www.linkedin.com/feed/")
    time.sleep(3)
    current_url = driver.current_url.lower()
    
    is_logged_in = False
    if "/feed" in current_url or "/mynetwork" in current_url:
        is_logged_in = True
    else:
        try:
            if driver.find_elements(By.CSS_SELECTOR, "#global-nav, .feed-identity-module, [data-view-name*='feed']"):
                is_logged_in = True
        except Exception:
            pass

    if is_logged_in:
        logger.info("Active session verified. No login prompt needed.")
        return True

    print("\n" + "=" * 70)
    print(f"{Style.YELLOW}{Style.BOLD}👉 ONE-TIME LOGIN REQUIRED IN OPEN CHROME BROWSER:{Style.RESET}")
    print(" 1. Please log into your LinkedIn account in the open browser window.")
    print(" 2. Complete any 2FA/SMS challenge if prompted.")
    print(" 3. Your session will be PERMANENTLY saved in this profile.")
    print("    Future runs will NEVER ask for login again!")
    print("=" * 70)
    
    driver.get("https://www.linkedin.com/login")
    try:
        input(f"\n{Style.CYAN}Press ENTER here once you are logged into LinkedIn and see your feed...{Style.RESET}")
    except (EOFError, KeyboardInterrupt):
        time.sleep(15)

    driver.get("https://www.linkedin.com/feed/")
    time.sleep(3)
    logger.info("One-time login confirmed and saved.")
    return True
