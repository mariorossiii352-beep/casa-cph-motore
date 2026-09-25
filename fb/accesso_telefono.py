"""Accesso a Facebook dal telefono, da solo (senza leggere i gruppi).

Lo lancia il workflow "accesso": apre la pagina di accesso nel vero Chrome, ne manda
l'immagine all'app, e quando sei entrato salva la sessione per il motore.
Regole del registro pubblico: solo numeri e parole fisse, niente dati.
"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from comune import accesso_remoto, SESSIONE, log
import motore_invio

minuti = int(sys.argv[1]) if len(sys.argv) > 1 else 30
with sync_playwright() as pw:
    cookie = accesso_remoto(pw, motore_invio.manda, time.time() + minuti * 60)
if not cookie:
    sys.exit(3)
SESSIONE.write_text(json.dumps({"cookies": cookie, "origins": []}), encoding="utf-8")
SESSIONE.with_suffix(".ok").write_text("1")
log("sessione nuova pronta")
