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
    r = page.evaluate("""async (u) => { const r = await fetch(u); const t = await r.text(); return {s: r.status, n: t.length, ok: t.startsWith('{"type":"data"')}; }""", DATI)
    log(f"__data.json: stato={r['s']} byte={r['n']} formato_giusto={r['ok']}")
    browser.close()
sys.exit(0)
