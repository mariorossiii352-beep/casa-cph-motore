"""Prova: Bolighub (protetto da Cloudflare) si legge da un browser vero su GitHub?
Nei registri pubblici solo numeri."""
import json, sys, time
from playwright.sync_api import sync_playwright
from comune import UA_ARGS, log

URL = "https://www.bolighub.dk/en/properties-to-rent?areas=K%C3%B8benhavn+K&max_monthly_rent=16000&sort_by=newest"
DATI = "https://www.bolighub.dk/en/properties-to-rent/__data.json?areas=K%C3%B8benhavn+K&max_monthly_rent=16000&sort_by=newest"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, args=UA_ARGS)
    ctx = browser.new_context(viewport={"width": 1260, "height": 860}, locale="en-GB", timezone_id="Europe/Copenhagen")
    page = ctx.new_page()
    t0 = time.time()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    for i in range(12):
        titolo = page.title()
        sfida = "moment" in titolo.lower()
        log(f"dopo {int(time.time() - t0)} s: sfida={sfida} lunghezza_pagina={len(page.content())}")
        if not sfida:
            break
        time.sleep(5)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(3)
    r = page.evaluate("""async (u) => { const r = await fetch(u); const t = await r.text(); return {s: r.status, n: t.length, ok: t.startsWith('{"type":"data"')}; }""", DATI)
    log(f"__data.json: stato={r['s']} byte={r['n']} formato_giusto={r['ok']}")
    t0 = time.time()
    quante = 0
    for a in ["K%C3%B8benhavn+V", "K%C3%B8benhavn+%C3%98", "K%C3%B8benhavn+N", "K%C3%B8benhavn+S"]:
        for pag in (1, 2):
            u = f"https://www.bolighub.dk/en/properties-to-rent/__data.json?areas={a}&max_monthly_rent=16000&sort_by=newest" + (f"&page={pag}" if pag > 1 else "")
            x = page.evaluate("async (u) => { const r = await fetch(u); const t = await r.text(); return [r.status, t.startsWith('{\"type\":\"data\"')]; }", u)
            quante += 1
            log(f"area {a[:12]} pagina {pag}: stato={x[0]} formato_giusto={x[1]}")
    log(f"{quante} richieste in {int(time.time() - t0)} s")
    browser.close()
sys.exit(0)
