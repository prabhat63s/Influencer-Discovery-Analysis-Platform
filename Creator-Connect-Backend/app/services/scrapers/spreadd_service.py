# Spreadd Service
# ===============
# Handles all interactions with Spreadd.io for influencer authenticity checking.
# Includes strict typing, robust error handling, and parallel execution capabilities.

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import time
import platform
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

from app.config.settings import settings
from app.services.data.memory_cache import cache
from app.services.reporting.monitoring_service import SearchMetrics

logger = logging.getLogger(__name__)

SPREADD_URL = settings.SPREADD_URL or "https://spreadd.io/tools/fake-follower-check/"


class AsyncSpreaddChecker:
    # Asynchronous wrapper for Selenium-based Spreadd.io checker.
    # Manages ChromeDriver lifecycle and provides async methods for username checks.

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None
        self._initialize_driver()

    def _initialize_driver(self) -> None:
        # Initialize ChromeDriver with robust binary detection and options.
        chrome_binary = self._find_chrome_binary()
        
        if not chrome_binary:
            raise RuntimeError("Chrome/Chromium browser not found on system. Please install Google Chrome.")

        logger.debug(f"Initializing ChromeDriver with binary: {chrome_binary}")
        
        chrome_options = Options()
        chrome_options.binary_location = chrome_binary
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--disable-infobars")
        
        # OS-specific optimizations
        if platform.system().lower() == "linux":
            chrome_options.add_argument("--single-process")
            
        # Suppress logging
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--silent")
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(10) # Standard implicit wait
            logger.info("✅ Spreadd Service: ChromeDriver initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ChromeDriver: {e}")
            raise

    def _find_chrome_binary(self) -> Optional[str]:
        # Locate Google Chrome or Chromium binary across different platforms.
        system = platform.system().lower()
        chrome_paths = []

        if system == "darwin":  # macOS
            chrome_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/opt/homebrew/bin/google-chrome",
                "/usr/local/bin/google-chrome",
                shutil.which("google-chrome"),
                shutil.which("chromium"),
            ]
        elif system == "linux":  # Linux
            chrome_paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/opt/google/chrome/chrome",
                "/snap/bin/chromium",
                shutil.which("google-chrome"),
                shutil.which("google-chrome-stable"),
            ]
        else:  # Windows/Other
            chrome_paths = [
                shutil.which("google-chrome"),
                shutil.which("chromium"),
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]

        # 1. Check direct paths
        for path in chrome_paths:
            if path and os.path.exists(path) and os.access(path, os.X_OK):
                return path

        # 2. Try mdfind on macOS
        if system == "darwin":
            try:
                result = subprocess.run(
                    ["mdfind", "kMDItemCFBundleIdentifier == 'com.google.Chrome'"],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    app_path = result.stdout.strip().split('\n')[0]
                    binary_path = os.path.join(app_path, "Contents/MacOS/Google Chrome")
                    if os.path.exists(binary_path) and os.access(binary_path, os.X_OK):
                        return binary_path
            except Exception:
                pass

        return None

    def close(self) -> None:
        # Clean up resources.
        if self.driver:
            try:
                self.driver.quit()
                logger.debug("ChromeDriver closed")
            except Exception as e:
                logger.warning(f"Error closing ChromeDriver: {e}")

    async def check_username(self, username: str) -> Dict[str, Any]:
        # Async entry point for username check.
        # Check cache
        cache_key = f"spreadd_check:{str(username).lower().strip()}"
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"⚡ Cache hit for Spreadd check: {username}")
            return cached

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._check_username_sync, username)
        
        # Cache successful results for 24 hours
        if result and result.get("followers") != "N/A":
            cache.set(cache_key, result, ttl_seconds=86400)

        return result

    def _check_username_sync(self, username: str) -> Dict[str, Any]:
        # Synchronous scraping logic for Spreadd.io.
        # Extracts followers, engagement rate, and authenticity percentages.
        uname = str(username).lstrip("@").strip()
        logger.debug(f"Checking @{uname} on Spreadd.io...")
        
        out = {
            "username": uname,
            "posts": "N/A",
            "followers": "N/A",
            "following": "N/A",
            "avg_likes": "N/A",
            "avg_comments": "N/A",
            "engagement_rate": "N/A",
            "real_followers_percentage": "N/A",
            "suspicious_followers_percentage": "N/A",
        }

        if not self.driver:
            logger.error("Driver not initialized")
            return out

        try:
            self.driver.get(SPREADD_URL)

            # Wait for search input (page is JS-rendered; try multiple selectors used by Spreadd.io)
            input_selectors = [
                'input[type="text"]',
                'input[type="search"]',
                'input[placeholder*="nstagram"]',
                'input[placeholder*="Instagram"]',
                'input[placeholder*="username"]',
                'input[name*="search"]',
                'input[name*="user"]',
                'input[aria-label*="search"]',
                'input[aria-label*="Instagram"]',
            ]
            input_elem = None
            wait = WebDriverWait(self.driver, timeout=10)
            for selector in input_selectors:
                try:
                    input_elem = wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if input_elem and input_elem.is_displayed():
                        break
                except (TimeoutException, Exception):
                    continue
            if not input_elem:
                # Last resort: first visible input in the main content
                try:
                    input_elem = wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "input"))
                    )
                except TimeoutException:
                    logger.warning("Could not find search input: no matching input element after 10s")
                    return out

            try:
                input_elem.clear()
                input_elem.send_keys(uname)

                # Try finding the check button
                try:
                    btn = self.driver.find_element(
                        By.XPATH,
                        '//button[contains(translate(.,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"check")]',
                    )
                    btn.click()
                except Exception:
                    input_elem.send_keys(Keys.RETURN)
            except Exception as e:
                logger.warning(f"Could not interact with search input: {e}")
                return out

            logger.debug(f"⏳ Waiting for Spreadd.io results for @{uname}...")
            # Wait for results to load - wait up to 20s for slow connections/processing
            time.sleep(10) 

            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            out.update(self._parse_spreadd_text(body_text))

            valid_data = out["followers"] != "N/A" or out["engagement_rate"] != "N/A"
            if valid_data:
                logger.info(f"✅ Spreadd.io found @{uname}: {out['followers']} followers, {out['engagement_rate']} metrics")
            else:
                logger.warning(f"⚠️ Spreadd.io: No data extracted for @{uname}")

        except Exception as e:
            logger.error(f"❌ Spreadd.io scraping error for @{uname}: {e}")
        
        return out

    def _parse_spreadd_text(self, text: str) -> Dict[str, str]:
        # Regex parsing of the page text to extract metrics.
        parsed = {}
        
        def find(*patterns):
            for pattern in patterns:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    return m.group(1).strip()
            return "N/A"

        parsed["posts"] = find(r'([\d,\.KkMm]+)\s*Posts?', r'Posts?[:\s]+([\d,\.KkMm]+)')
        parsed["followers"] = find(r'([\d,\.KkMm]+)\s*Followers?', r'Followers?[:\s]+([\d,\.KkMm]+)')
        parsed["following"] = find(r'([\d,\.KkMm]+)\s*Following', r'Following[:\s]+([\d,\.KkMm]+)')
        parsed["avg_likes"] = find(r'([\d,\.KkMm]+)\s*Avg\.?\s*Likes?', r'Avg\.?\s*Likes?[:\s]+([\d,\.KkMm]+)')
        parsed["avg_comments"] = find(r'([\d,\.KkMm]+)\s*Avg\.?\s*Comments?', r'Avg\.?\s*Comments?[:\s]+([\d,\.KkMm]+)')
        parsed["engagement_rate"] = find(r'([\d\.]+%)\s*Engagement', r'Engagement[:\s]+([\d\.]+%)')
        
        parsed["real_followers_percentage"] = find(
            r'([\d\.]+%)\s*Real', r'Real[:\s]+([\d\.]+%)',
            r'Authentic[:\s]+([\d\.]+%)', r'([\d\.]+%)\s*Authentic'
        )
        parsed["suspicious_followers_percentage"] = find(
            r'([\d\.]+%)\s*Suspicious', r'Suspicious[:\s]+([\d\.]+%)',
            r'Fake[:\s]+([\d\.]+%)', r'([\d\.]+%)\s*Fake'
        )
        
        # Fallback for "85% real, 15% fake" strings if individual matches fail
        if parsed["real_followers_percentage"] == "N/A":
            match = re.search(r'([\d\.]+)%\s*(?:real|authentic).*?([\d\.]+)%\s*(?:fake|suspicious)', text, re.IGNORECASE)
            if match:
                parsed["real_followers_percentage"] = f"{match.group(1)}%"
                parsed["suspicious_followers_percentage"] = f"{match.group(2)}%"

        return parsed


# ============================================================================
# SERVICE HELPER: PARALLEL EXECUTION
# ============================================================================

async def run_spreadd_parallel(
    unique_results: List[Dict],
    metrics: Optional[SearchMetrics] = None
) -> None:
    """
    Run Spreadd checks in parallel for a list of influencers.
    Updates the dictionaries in-place with authenticity scores.
    """
    targets = [
        r for r in unique_results 
        if r.get("username") or r.get("Id") or r.get("NAME")
    ]
    
    if not targets:
        return

    logger.info(f"🔄 Starting Spreadd Service for {len(targets)} profiles (Parallel)")
    
    # Use a checker instance
    # NOTE: Selenium isn't thread-safe, so we need one driver per concurrent task
    # OR we invoke one checker serially. 
    # For true parallelism with Selenium, we need multiple drivers, which is heavy.
    # We will limit concurrency to avoid OOM or chrome spawn storms.
    MAX_CONCURRENT_BROWSERS = 2 
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)

    async def secure_check(res: Dict):
        username = res.get("username") or res.get("Id") or res.get("NAME")
        if not username:
            return

        async with semaphore:
            checker = None
            try:
                # Instantiate fresh checker per task to ensure clean state
                # This is expensive but safe. Optimizing this would require a pool.
                checker = AsyncSpreaddChecker(headless=True)
                data = await checker.check_username(username)
                
                # Update result in-place
                if data["real_followers_percentage"] != "N/A":
                    res["real_followers_percentage"] = data["real_followers_percentage"]
                if data["suspicious_followers_percentage"] != "N/A":
                    res["suspicious_followers_percentage"] = data["suspicious_followers_percentage"]
                if data["engagement_rate"] != "N/A":
                    res["engagement_rate"] = data["engagement_rate"]  # Spreadd is often more accurate
                
                # Fill missing basic metrics if needed
                if res.get("followers", "N/A") in ["N/A", "0"] and data["followers"] != "N/A":
                    res["followers"] = data["followers"]
                
                if metrics:
                    metrics.spreadd_successful_checks += 1
                    
            except Exception as e:
                logger.error(f"Failed Spreadd check for {username}: {e}")
                if metrics:
                    metrics.add_error(f"Spreadd failed for {username}: {e}")
            finally:
                if checker:
                    checker.close()

    # Create tasks
    tasks = [secure_check(res) for res in targets]
    await asyncio.gather(*tasks)
    logger.info(f"✅ Spreadd Service completed for {len(targets)} profiles")
