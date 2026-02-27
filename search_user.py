"""Search for user 治雨 on Xueqiu"""
import sys, io, time, json
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
ctx = browser.contexts[0]
page = ctx.new_page()

page.goto("https://xueqiu.com/k?q=%E6%B2%BB%E9%9B%A8&forceRedirect=1&page=1&type=user",
          wait_until="domcontentloaded", timeout=15000)
page.wait_for_timeout(5000)

users = page.evaluate("""() => {
    const cards = document.querySelectorAll('.search__user__card__content');
    const result = [];
    for (const card of cards) {
        const nameEl = card.querySelector('.user-name');
        const descEl = card.querySelector('p');
        result.push({
            name: nameEl ? nameEl.textContent.trim() : '',
            href: nameEl ? nameEl.getAttribute('href') : '',
            desc: descEl ? descEl.textContent.trim().substring(0, 80) : ''
        });
    }
    if (!result.length) {
        const anchors = document.querySelectorAll('a.user-name');
        for (const a of anchors) {
            result.push({
                name: a.textContent.trim(),
                href: a.getAttribute('href') || ''
            });
        }
    }
    return result;
}""")
print(json.dumps(users, ensure_ascii=False, indent=2))

page.close()
browser.close()
pw.stop()
