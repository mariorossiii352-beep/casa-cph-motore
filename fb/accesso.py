"""Accesso a Facebook fatto a mano dall'utente, dentro il browser del server.

Il browser e' visibile da una pagina VNC protetta da password. Questo script
aspetta che l'accesso sia completo e poi chiude, cosi' il profilo si salva.
"""
import sys, time
from playwright.sync_api import sync_playwright
from comune import apri, stato, log

MINUTI = int(sys.argv[1]) if len(sys.argv) > 1 else 25

with sync_playwright() as pw:
    ctx, page = apri(pw)
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    log(f"browser pronto: hai {MINUTI} minuti per entrare in Facebook")
    fine = time.time() + MINUTI * 60
    while time.time() < fine and stato(ctx, page) != "collegato":
        time.sleep(10)
    if stato(ctx, page) != "collegato":
        log("accesso NON completato")
        ctx.close()
        sys.exit(1)
    log("accesso completato: resto aperto 90 secondi per finire di caricare")
    time.sleep(90)
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    time.sleep(10)
    ok = stato(ctx, page) == "collegato"
    ctx.close()
    log("sessione salvabile" if ok else "sessione persa dopo l'accesso")
    sys.exit(0 if ok else 1)
