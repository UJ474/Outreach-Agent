"""
scraper.py — Scrapes company websites using Playwright.
Keeps page text under 1500 chars to stay within Groq token budget.
"""

import asyncio
from playwright.async_api import async_playwright


async def scrape_company(url: str, max_chars: int = 1500) -> str:
    """
    Visits the given URL and returns cleaned page text, capped at max_chars.
    Returns an error string if scraping fails.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # Wait until network is mostly idle (good for JS-heavy sites)
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Extract visible text by evaluating in-browser
            raw_text = await page.evaluate("""
                () => {
                    // Remove script/style/nav/footer noise
                    const remove = document.querySelectorAll(
                        'script, style, nav, footer, header, noscript, svg'
                    );
                    remove.forEach(el => el.remove());

                    return document.body.innerText;
                }
            """)

            # Clean up whitespace
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            cleaned = " ".join(lines)

            # Truncate to token-safe length
            return cleaned[:max_chars]

        except Exception as e:
            return f"ERROR scraping {url}: {e}"

        finally:
            await browser.close()


def scrape(url: str, max_chars: int = 1500) -> str:
    """Synchronous wrapper — call this from agent.py."""
    return asyncio.run(scrape_company(url, max_chars))


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_url = "https://www.notion.so"
    print(f"Scraping: {test_url}\n")
    result = scrape(test_url)
    print(result)
    print(f"\n--- {len(result)} chars scraped ---")
