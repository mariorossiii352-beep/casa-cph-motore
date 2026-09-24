"""Pezzi comuni: browser, lettura dei dati GraphQL, stato della sessione.

Regola per tutto il motore: il repository e' pubblico e i registri di GitHub li
vede chiunque. Nei registri si scrivono solo numeri, mai testi, nomi o link.
"""
import json, re, time, datetime
from pathlib import Path


UA_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]


def log(*a):
    print(datetime.datetime.utcnow().strftime("%H:%M:%S"), *a, flush=True)


SESSIONE = Path.home() / "sessione.json"


def apri(pw):
    """Browser con la sessione salvata (cookie), che alla fine va risalvata con salva()."""
    browser = pw.chromium.launch(headless=False, args=UA_ARGS)
    ctx = browser.new_context(storage_state=str(SESSIONE), viewport={"width": 1260, "height": 860},
                              locale="da-DK", timezone_id="Europe/Copenhagen")
    page = ctx.new_page()
    return ctx, page


def salva(ctx):
    SESSIONE.write_text(json.dumps(ctx.storage_state()), encoding="utf-8")
    # Segnale per GitHub: in questo giro la sessione era collegata, si puo' ricaricare.
    SESSIONE.with_suffix(".ok").write_text("1")


SEGNI = {
    "login": r'name="email"|name="pass"|Log ind på Facebook|Log in to Facebook|Log into Facebook',
    "verifica": r"checkpoint|Bekræft din identitet|Confirm your identity|Vi har brug for at bekræfte|security check",
    "bloccato": r"midlertidigt blokeret|temporarily blocked|You.re Temporarily Blocked|misusing this feature|going too fast",
    "non_disponibile": r"content isn.t available|indhold er ikke tilg.ngeligt|Dette indhold er ikke",
    "iscrizione": r"Deltag i gruppe|Join group|Bliv medlem",
}


def diagnosi_pagina(page):
    """Cosa mostra davvero la pagina (per il canale privato verso l'app, mai per i registri)."""
    try:
        html = page.content()
    except Exception:
        html = ""
    try:
        testo = page.inner_text("body")[:600]
    except Exception:
        testo = ""
    try:
        articoli = page.locator('[role="article"]').count()
    except Exception:
        articoli = -1
    segni = [k for k, rx in SEGNI.items() if re.search(rx, html, re.I)]
    return {"url": page.url[:200], "titolo": (page.title() or "")[:120], "segni": segni,
            "articoli": articoli, "c_user": "c_user" in {c["name"] for c in page.context.cookies("https://www.facebook.com")},
            "testo": re.sub(r"\s+", " ", testo)[:400]}


def stato(ctx, page):
    if "checkpoint" in page.url or "/login" in page.url or "two_step" in page.url:
        return "verifica"
    nomi = {c["name"] for c in ctx.cookies("https://www.facebook.com")}
    return "collegato" if "c_user" in nomi else "scollegato"


def oggetti(body):
    if body.lstrip().startswith("<"):
        for m in re.finditer(r'<script type="application/json"[^>]*>(.*?)</script>', body, re.S):
            try:
                yield json.loads(m.group(1))
            except Exception:
                pass
        return
    for riga in body.splitlines():
        if riga.strip().startswith("{"):
            try:
                yield json.loads(riga)
            except Exception:
                pass


def cammina(o, f):
    if isinstance(o, dict):
        f(o)
        for v in o.values():
            cammina(v, f)
    elif isinstance(o, list):
        for v in o:
            cammina(v, f)


def post_da(risposte):
    """Tutti i post (Story) trovati nelle risposte, con testo, data e foto."""
    tutti = {}
    for body in risposte:
        for obj in oggetti(body):
            def visita(d):
                if d.get("__typename") != "Story" or not d.get("post_id"):
                    return
                p = tutti.setdefault(d["post_id"], {"id": d["post_id"], "testo": "", "tempo": None,
                                                    "foto": {}, "foto_totali": 0, "url": None})
                def dentro(x):
                    if isinstance(x.get("creation_time"), int) and not p["tempo"]:
                        p["tempo"] = x["creation_time"]
                    m = x.get("message")
                    if isinstance(m, dict) and isinstance(m.get("text"), str) and len(m["text"]) > len(p["testo"]):
                        p["testo"] = m["text"]
                    if x.get("__typename") == "Photo" and x.get("id"):
                        img = x.get("image") or x.get("viewer_image") or {}
                        if isinstance(img, dict) and img.get("uri"):
                            p["foto"][x["id"]] = img["uri"]
                        else:
                            p["foto"].setdefault(x["id"], None)
                    s = x.get("all_subattachments")
                    if isinstance(s, dict) and isinstance(s.get("count"), int):
                        p["foto_totali"] = max(p["foto_totali"], s["count"])
                    if isinstance(x.get("url"), str) and "/groups/" in x["url"] and not p["url"]:
                        p["url"] = x["url"]
                cammina(d, lambda x: isinstance(x, dict) and dentro(x))
            cammina(obj, visita)
    return tutti


def registra(page, azione):
    """Esegue azione() raccogliendo le risposte GraphQL e la pagina iniziale."""
    risposte = []
    def on_resp(r):
        if "/api/graphql" in r.url or r.request.resource_type == "document":
            try:
                risposte.append(r.text())
            except Exception:
                pass
    page.on("response", on_resp)
    try:
        azione()
    finally:
        page.remove_listener("response", on_resp)
    return risposte


def leggi_gruppo(page, gid, scroll=12):
    def azione():
        page.goto(f"https://www.facebook.com/groups/{gid}/?sorting_setting=CHRONOLOGICAL",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        page.keyboard.press("Escape")
        for _ in range(scroll):
            page.mouse.move(600, 500)
            page.mouse.wheel(0, 2500)
            time.sleep(2.2)
        time.sleep(2)
    return post_da(registra(page, azione))
