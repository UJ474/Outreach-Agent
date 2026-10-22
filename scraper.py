"""
scraper.py — Multi-page website scraper using Playwright.
Scrapes homepage + internal pages + extra URLs for each lead.
"""

import asyncio
import random
import logging
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Internal paths to try, in order
INTERNAL_PATHS = [
    "/about",
    "/blog", "/news", "/changelog",
    "/careers", "/jobs",
]

MAX_INTERNAL_PAGES = 4
MAX_CHARS_PER_PAGE = 2500
TOTAL_CHAR_CAP = 8000
PAGE_TIMEOUT_MS = 20000

# JS to clean and extract text
EXTRACT_JS = """
() => {
    const remove = document.querySelectorAll(
        'nav, footer, script, style, noscript, svg, header'
    );
    remove.forEach(el => el.remove());
    return document.body ? document.body.innerText : '';
}
"""


async def _scrape_page(page, url: str) -> str | None:
    """Scrape a single page. Returns cleaned text or None on failure."""
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        if resp and resp.status >= 400:
            logger.debug(f"  HTTP {resp.status} for {url}")
            return None

        raw_text = await page.evaluate(EXTRACT_JS)
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        cleaned = " ".join(lines)

        # If too short, retry with networkidle
        if len(cleaned) < 300:
            try:
                await page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
                raw_text = await page.evaluate(EXTRACT_JS)
                lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
                cleaned = " ".join(lines)
            except Exception:
                pass  # Use whatever we got

        return cleaned[:MAX_CHARS_PER_PAGE] if cleaned else None

    except Exception as e:
        logger.debug(f"  Failed to scrape {url}: {e}")
        return None


async def _scrape_site_async(website: str, extra_urls: str = "") -> dict:
    """
    Scrape a site: homepage + internal pages + extra_urls.
    Returns {url: text} dict.
    """
    results = {}
    total_chars = 0

    parsed = urlparse(website)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Build list of URLs to try
    urls_to_try = [website]

    # Internal paths — deduplicate by group (e.g., /blog OR /news, not both)
    seen_groups = set()
    groups = {
        "/about": "about",
        "/blog": "blog", "/news": "blog", "/changelog": "blog",
        "/careers": "careers", "/jobs": "careers",
    }
    for path in INTERNAL_PATHS:
        group = groups.get(path, path)
        if group not in seen_groups:
            urls_to_try.append(urljoin(base_url, path))
            seen_groups.add(group)
        if len(urls_to_try) > MAX_INTERNAL_PAGES:
            break

    # Limit internal pages
    urls_to_try = urls_to_try[:MAX_INTERNAL_PAGES + 1]  # +1 for homepage

    # Add extra URLs
    extra_list = []
    if extra_urls:
        for u in extra_urls.split(";"):
            u = u.strip()
            if u:
                extra_list.append(u)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # Scrape internal pages
            for i, url in enumerate(urls_to_try):
                if total_chars >= TOTAL_CHAR_CAP:
                    break

                text = await _scrape_page(page, url)
                if text:
                    results[url] = text
                    total_chars += len(text)
                    logger.debug(f"  Scraped {url} ({len(text)} chars)")

                # Polite delay between pages on same site
                if i < len(urls_to_try) - 1:
                    await asyncio.sleep(random.uniform(1.0, 2.0))

            # Scrape extra URLs
            for url in extra_list:
                if total_chars >= TOTAL_CHAR_CAP:
                    break

                await asyncio.sleep(random.uniform(1.0, 2.0))
                text = await _scrape_page(page, url)
                if text:
                    results[url] = text
                    total_chars += len(text)
                    logger.debug(f"  Scraped extra {url} ({len(text)} chars)")

        finally:
            await browser.close()

    return results


def scrape_site(website: str, extra_urls: str = "") -> dict:
    """Synchronous wrapper. Returns {url: text} dict."""
    return asyncio.run(_scrape_site_async(website, extra_urls))


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test_url = "https://www.notion.so"
    print(f"Scraping: {test_url}\n")
    result = scrape_site(test_url)
    for url, text in result.items():
        print(f"\n--- {url} ({len(text)} chars) ---")
        print(text[:200] + "...")
    print(f"\nTotal pages: {len(result)}")
