"""Prova: legge tutti i gruppi a giro per N minuti e scrive solo i numeri."""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from comune import apri, stato, log, leggi_gruppo

MINUTI = int(sys.argv[1]) if len(sys.argv) > 1 else 40
GRUPPI = json.loads((Path(__file__).parent / "gruppi.json").read_text())

with sync_playwright() as pw:
    ctx, page = apri(pw)
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    time.sleep(8)
    s = stato(ctx, page)
    log("stato iniziale:", s)
    if s != "collegato":
        ctx.close()
        log("ALLARME: sessione non valida all'avvio")
        sys.exit(2)
    fine = time.time() + MINUTI * 60
    giro = 0
    esito = 0
    while time.time() < fine and esito == 0:
        giro += 1
        visti, recenti, senza_testo, n = 0, 0, 0, 0
        for i, gid in enumerate(GRUPPI):
            if time.time() > fine:
                break
            try:
                posts = leggi_gruppo(page, gid)
            except Exception as e:
                log(f"giro {giro} gruppo #{i}: errore {type(e).__name__}")
                continue
            s = stato(ctx, page)
            if s != "collegato":
                log(f"ALLARME giro {giro} gruppo #{i}: stato={s}")
                esito = 3
                break
            ora = time.time()
            r24 = sum(1 for p in posts.values() if p["tempo"] and ora - p["tempo"] < 86400)
            st = sum(1 for p in posts.values() if not p["testo"])
            log(f"giro {giro} gruppo #{i}: post={len(posts)} ultime24h={r24} senza_testo={st}")
            visti += len(posts); recenti += r24; senza_testo += st; n += 1
        log(f"FINE GIRO {giro}: gruppi={n}/{len(GRUPPI)} post={visti} ultime24h={recenti} senza_testo={senza_testo}")
    ctx.close()
    sys.exit(esito)
