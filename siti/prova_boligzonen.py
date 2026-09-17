"""Prova: Boligzonen da GitHub con un browser vero (visibile su schermo virtuale),
lasciando il tempo di superare il controllo di Cloudflare. Scrive solo numeri e titoli."""
import time
from playwright.sync_api import sync_playwright

LISTA = "https://boligzonen.dk/lejebolig?property_search%5Bsort%5D=updated_at&sort=updated_at"


def aspetta_controllo(page, secondi=60):
    fine = time.time() + secondi
    while time.time() < fine:
        titolo = page.title()
        html = page.content()
        if "Just a moment" not in titolo and "Attention Required" not in titolo and "challenge" not in html[:3000].lower():
            return titolo, html
        time.sleep(2)
    return page.title(), page.content()


with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        "/tmp/profilo-bz", headless=False, viewport={"width": 1280, "height": 860},
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"], locale="da-DK", timezone_id="Europe/Copenhagen")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    r = page.goto(LISTA, wait_until="domcontentloaded", timeout=60000)
    print("prima risposta:", r.status if r else None, "titolo:", page.title())
    t0 = time.time()
    titolo, html = aspetta_controllo(page)
    print(f"dopo {round(time.time() - t0)} s -> titolo: {titolo[:60]} | CollectionPage: {'CollectionPage' in html} | lunghezza {len(html)}")
    if "CollectionPage" in html:
        link = page.locator('a[href*="/lejeboliger/"]').first.get_attribute("href")
        r2 = page.goto(("https://boligzonen.dk" + link) if link.startswith("/") else link, wait_until="domcontentloaded", timeout=60000)
        t2, h2 = aspetta_controllo(page, 30)
        print("scheda:", r2.status if r2 else None, "| RealEstateListing:", "RealEstateListing" in h2, "| descrizione intera:", "show-more-content" in h2)
        r3 = page.request.get(LISTA + "&page=2")
        print("pagina 2 con richiesta diretta dal browser:", r3.status, "CollectionPage" in r3.text())
        for i in range(3, 8):
            page.goto(LISTA + f"&page={i}", wait_until="domcontentloaded", timeout=60000)
            ti, hi = aspetta_controllo(page, 30)
            print(f"pagina {i}: CollectionPage {'CollectionPage' in hi}")
            time.sleep(2)
    else:
        print("inizio pagina:", html[:300].replace("\n", " "))
    ctx.close()
