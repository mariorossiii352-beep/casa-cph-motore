"""Prova: Boligzonen si lascia leggere da GitHub? Semplice richiesta e browser vero."""
import json, time, urllib.request
from playwright.sync_api import sync_playwright

URL_LISTA = "https://boligzonen.dk/lejebolig?property_search%5Bsort%5D=updated_at&sort=updated_at"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

def semplice():
    req = urllib.request.Request(URL_LISTA, headers={"User-Agent": UA, "Accept": "text/html", "Accept-Language": "da-DK,da;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read().decode("utf-8", "ignore")
            return r.status, len(t), "Just a moment" in t
    except urllib.error.HTTPError as e:
        return e.code, 0, None

print("richiesta semplice:", semplice())

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    p = b.new_page(user_agent=UA, locale="da-DK")
    r = p.goto(URL_LISTA, wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)
    html = p.content()
    print("browser lista:", r.status if r else None, len(html), "sfida" if "Just a moment" in html else "ok",
          "annunci json-ld" if "CollectionPage" in html else "niente json-ld")
    link = None
    for a in p.locator('a[href*="/lejeboliger/"]').all()[:3]:
        link = a.get_attribute("href")
        if link:
            break
    if link:
        r2 = p.goto("https://boligzonen.dk" + link if link.startswith("/") else link, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        h2 = p.content()
        print("browser scheda:", r2.status if r2 else None, len(h2), "RealEstateListing" in h2)
        # Dopo aver superato la pagina, le richieste dallo stesso browser passano?
        r3 = p.request.get(URL_LISTA + "&page=2")
        print("richiesta dal browser (pagina 2):", r3.status, len(r3.text()))
    b.close()
