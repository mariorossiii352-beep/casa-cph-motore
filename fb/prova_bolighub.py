"""Prova: Bolighub (protetto da Cloudflare) si legge da un browser vero su GitHub?
Nei registri pubblici solo numeri."""
import sys, time
from playwright.sync_api import sync_playwright
from comune import UA_ARGS, log

URL = "https://www.bolighub.dk/en/properties-to-rent?areas=K%C3%B8benhavn+K&max_monthly_rent=16000&sort_by=newest"
BASE = "https://www.bolighub.dk/en/properties-to-rent/__data.json?max_monthly_rent=16000&sort_by=newest&areas="


JS = "async (u) => { const r = await fetch(u, {credentials: 'include'}); const t = await r.text(); return [r.status, t.length, t.startsWith('{\"type\":\"data\"')]; }"


def leggi(page, area, pag=1):
    u = BASE + area + (f"&page={pag}" if pag > 1 else "")
    for tentativo in range(6):
        try:
            return page.evaluate(JS, u)
        except Exception as e:
            if "context was destroyed" not in str(e):
                raise
            time.sleep(3)
    return [0, 0, "pagina_instabile"]


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, args=UA_ARGS)
    ctx = browser.new_context(viewport={"width": 1260, "height": 860}, locale="en-GB", timezone_id="Europe/Copenhagen")
    page = ctx.new_page()
    t0 = time.time()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)
    page.wait_for_load_state("load", timeout=30000)
    log(f"url_finale_ok={'bolighub.dk/en/properties-to-rent' in page.url}")
    log(f"titolo_contiene_moment={'moment' in page.title().lower()} pagina_byte={len(page.content())} cookie={len(ctx.cookies())}")
    n = 0
    for a in ["K%C3%B8benhavn+K", "K%C3%B8benhavn+V", "K%C3%B8benhavn+%C3%98", "K%C3%B8benhavn+N", "K%C3%B8benhavn+S"]:
        for pag in (1, 2):
            try:
                s, b, ok = leggi(page, a, pag)
            except Exception as e:
                s, b, ok = 0, 0, type(e).__name__
            n += 1
            log(f"zona {a[-6:]} pagina {pag}: stato={s} byte={b} formato_giusto={ok}")
    log(f"{n} richieste in {int(time.time() - t0)} s")
    browser.close()
sys.exit(0)
