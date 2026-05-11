import asyncio
import random

from playwright.async_api import async_playwright

BROWSER = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36"
]


async def get_browser():

    global BROWSER

    if BROWSER:
        return BROWSER

    playwright = await async_playwright().start()

    BROWSER = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox"
        ]
    )

    return BROWSER


async def apply_stealth(page):

    await page.add_init_script("""
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

window.chrome = {
    runtime: {}
};

Object.defineProperty(navigator, 'plugins', {
    get: () => [1,2,3,4,5]
});

Object.defineProperty(navigator, 'languages', {
    get: () => ['ru-RU', 'ru']
});
    """)


async def search_iparts(query: str):

    browser = await get_browser()

    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={
            "width": 1366,
            "height": 768
        },
        locale="ru-RU"
    )

    page = await context.new_page()

    await apply_stealth(page)

    results = []

    try:

        await page.goto(
            f"https://iparts.by/search/?q={query}",
            timeout=90000,
            wait_until="domcontentloaded"
        )

        await page.wait_for_timeout(
            random.randint(2500, 5000)
        )

        body = await page.content()

        if "captcha" in body.lower():
            return []

        cards = await page.query_selector_all("article")

        if not cards:
            cards = await page.query_selector_all("div")

        for card in cards:

            try:

                text = await card.inner_text()

                if not text:
                    continue

                if "BYN" not in text:
                    continue

                if len(text) > 500:
                    continue

                lines = [
                    x.strip()
                    for x in text.split("\\n")
                    if x.strip()
                ]

                if len(lines) < 2:
                    continue

                name = lines[0][:150]

                price = "Не указана"

                for line in lines:

                    if "BYN" in line:
                        price = line
                        break

                link_el = await card.query_selector("a")

                link = ""

                if link_el:
                    href = await link_el.get_attribute("href")

                    if href:

                        if href.startswith("/"):
                            link = "https://iparts.by" + href
                        else:
                            link = href

                img = ""

                img_el = await card.query_selector("img")

                if img_el:
                    src = await img_el.get_attribute("src")

                    if src:
                        img = src

                results.append({
                    "name": name,
                    "price": price,
                    "link": link,
                    "image": img
                })

            except:
                pass

            if len(results) >= 15:
                break

    except Exception as e:
        print("PARSER ERROR:", e)

    finally:

        await context.close()

    return results