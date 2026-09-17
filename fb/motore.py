"""Motore Facebook: legge i gruppi a giro continuo e manda i post nuovi all'app.

Regole del registro pubblico: solo numeri. Nessun testo, nome o link.
"""
import json, os, sys, time, hashlib, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
from comune import apri, salva, stato, log, leggi_gruppo, registra, post_da

APP = "https://casa-cph-nuova.mariorossiii352.workers.dev"
MINUTI = int(sys.argv[1]) if len(sys.argv) > 1 else 330
GRUPPI = json.loads((Path(__file__).parent / "gruppi.json").read_text())
MEMORIA = Path.home() / "memoria-fb" / "visti.json"


def token_github():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=casa-cph"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["value"]


def manda(percorso, dati):
    corpo = json.dumps(dati).encode()
    for tentativo in range(3):
        try:
            req = urllib.request.Request(APP + percorso, data=corpo, method="POST",
                                         headers={"Authorization": "Bearer " + token_github(), "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            log(f"invio {percorso} tentativo {tentativo + 1}: {type(e).__name__}")
            time.sleep(10)
    return None


def firma(p):
    return hashlib.sha1(f"{p['testo']}|{len(p['foto'])}|{p['foto_totali']}".encode()).hexdigest()[:16]


def tutte_le_foto(page, post_id):
    """Le foto di un post dall'album pcb.<id>: il feed ne da' al massimo 5."""
    import time as t
    def azione():
        page.goto(f"https://www.facebook.com/media/set/?set=pcb.{post_id}&type=1", wait_until="domcontentloaded", timeout=60000)
        t.sleep(5)
        page.keyboard.press("Escape")
        for _ in range(6):
            page.mouse.move(600, 500)
            page.mouse.wheel(0, 3000)
            t.sleep(1.3)
    risposte = registra(page, azione)
    from comune import oggetti, cammina
    foto = {}
    def visita(d):
        if d.get("__typename") == "Photo" and d.get("id"):
            for k in ("image", "viewer_image", "photo_image"):
                v = d.get(k)
                if isinstance(v, dict) and v.get("uri"):
                    w = v.get("width") or 0
                    if w >= foto.get(d["id"], (0, None))[0]:
                        foto[d["id"]] = (w, v["uri"])
    for b in risposte:
        for o in oggetti(b):
            cammina(o, lambda x: isinstance(x, dict) and visita(x))
    return [u for _, u in foto.values()]


MEMORIA.parent.mkdir(parents=True, exist_ok=True)
visti = json.loads(MEMORIA.read_text()) if MEMORIA.exists() else {}
fine = time.time() + MINUTI * 60
esito = 0

with sync_playwright() as pw:
    ctx, page = apri(pw)
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    time.sleep(8)
    if stato(ctx, page) != "collegato":
        manda("/motore/stato", {"allarme": "la sessione non e' piu' valida (Facebook ha scollegato l'account o chiede una verifica)"})
        log("ALLARME: sessione non valida")
        sys.exit(3)
    giro = 0
    while time.time() < fine and esito == 0:
        giro += 1
        t0 = time.time()
        letti = nuovi = offerte = errori = 0
        for i, gid in enumerate(GRUPPI):
            if time.time() > fine:
                break
            try:
                posts = leggi_gruppo(page, gid)
            except Exception as e:
                errori += 1
                log(f"giro {giro} gruppo #{i}: errore {type(e).__name__}")
                continue
            if stato(ctx, page) != "collegato":
                manda("/motore/stato", {"allarme": "Facebook chiede una verifica o ha scollegato l'account"})
                log(f"ALLARME giro {giro} gruppo #{i}")
                esito = 3
                break
            letti += len(posts)
            da_mandare = []
            for p in posts.values():
                if not p["testo"] and not p["foto"]:
                    continue
                pp = {"id": p["id"], "url": p["url"], "testo": p["testo"], "tempo": p["tempo"],
                      "foto": [u for u in p["foto"].values() if u], "foto_totali": p["foto_totali"]}
                f = firma(pp)
                if visti.get(p["id"]) == f:
                    continue
                da_mandare.append((pp, f))
            for k in range(0, len(da_mandare), 5):
                blocco = da_mandare[k:k + 5]
                r = manda("/motore/facebook", {"gruppo": gid, "posts": [x[0] for x in blocco]})
                if r is None:
                    errori += 1
                    continue
                for pp, f in blocco:
                    visti[pp["id"]] = f
                nuovi += len(blocco)
                salvati = r.get("salvato", 0)
                offerte += salvati
                # Le offerte con piu' foto di quelle arrivate dal feed: si prendono tutte e si rimanda.
                if salvati:
                    for pp, f in blocco:
                        if pp["foto_totali"] > len(pp["foto"]):
                            try:
                                foto = tutte_le_foto(page, pp["id"])
                            except Exception:
                                continue
                            if len(foto) > len(pp["foto"]):
                                pp2 = dict(pp, foto=foto, foto_totali=max(len(foto), pp["foto_totali"]))
                                if manda("/motore/facebook", {"gruppo": gid, "posts": [pp2]}) is not None:
                                    visti[pp["id"]] = firma(pp2)
            log(f"giro {giro} gruppo #{i}: post={len(posts)} inviati={len(da_mandare)}")
        durata = round((time.time() - t0) / 60)
        log(f"FINE GIRO {giro}: post={letti} nuovi={nuovi} offerte={offerte} errori={errori} minuti={durata}")
        manda("/motore/stato", {"post": letti, "note": f"giro {giro}: {len(GRUPPI)} gruppi in {durata} min, {nuovi} post nuovi, {offerte} offerte"})
        # Tiene la memoria piccola: bastano i post degli ultimi giorni.
        if len(visti) > 20000:
            visti = dict(list(visti.items())[-12000:])
        MEMORIA.write_text(json.dumps(visti))
    if esito == 0:
        salva(ctx)
    ctx.close()
MEMORIA.write_text(json.dumps(visti))
sys.exit(esito)
