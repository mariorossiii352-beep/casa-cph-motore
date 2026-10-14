"""Bolighub (bolighub.dk): lo legge un browser vero e manda i dati all'app.

Dal 13/10/2026 il sito mette la sfida di Cloudflare ("Just a moment", HTTP 403) su ogni richiesta che non viene da un
browser vero: Cloudflare, il PC e il ponte in Europa ricevono 403. Un browser vero su GitHub apre le pagine (elenco di una
zona, scheda di un annuncio) e la pagina contiene gia' i dati dentro lo script che la avvia ("kit.start(... data: [...])").
Le richieste "dati" (__data.json) invece restano bloccate anche dal browser: per questo si apre la pagina vera.

L'app decide cosa leggere: a ogni chiamata manda l'elenco delle pagine che le servono ancora ("da_leggere"), qui si aprono e
si rimandano i risultati, finche' non manca piu' niente. Il ciclo si ripete ogni ~10 minuti.

Regole del registro pubblico: solo numeri. Nessun testo, nome o link.
"""
import sys, time
from playwright.sync_api import sync_playwright
from comune import UA_ARGS, log
from motore_invio import manda

# Solo i campi che servono all'app (la pagina ne contiene molti altri, pesanti).
JS_NODI = r"""() => {
  const KEEP = ['listingCount', 'initialListings', 'rentalData', 'staticData', 'address', 'description', 'contactMethod', 'imageUrls'];
  const t = [...document.scripts].map((x) => x.textContent).find((x) => x.includes('kit.start'));
  if (!t) return null;
  const m = /data:\s*(\[[\s\S]*\])\s*,\s*form:\s*null/.exec(t);
  if (!m) return null;
  const nodi = new Function('return ' + m[1])();
  return nodi.filter((n) => n && n.type === 'data' && n.data)
    .map((n) => ({ type: 'data', data: Object.fromEntries(Object.entries(n.data).filter(([k]) => KEEP.includes(k))) }));
}"""

PAUSA = 1.0          # secondi tra una pagina e l'altra
MAX_PER_GIRO = 70    # pagine per chiamata
MAX_GIRI = 8         # chiamate per ciclo
CICLO_S = 600        # un ciclo ogni ~10 minuti


def sfida(page):
    try:
        return "moment" in page.title().lower()
    except Exception:
        return True


def leggi(page, url):
    """Apre la pagina e restituisce {url, stato, finale, nodi}."""
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        stato = resp.status if resp else 0
        # La sfida di Cloudflare si risolve da sola in pochi secondi nel browser vero.
        for _ in range(10):
            if not sfida(page):
                break
            time.sleep(2)
        if sfida(page):
            return {"url": url, "stato": 403, "finale": page.url, "nodi": None}
        if stato == 403:
            stato = 200  # era la pagina della sfida, poi la pagina vera
        nodi = None
        for _ in range(3):
            try:
                nodi = page.evaluate(JS_NODI)
                break
            except Exception:
                time.sleep(2)  # la pagina si sta ricaricando
        return {"url": url, "stato": stato, "finale": page.url, "nodi": nodi}
    except Exception as e:
        log(f"pagina non letta: {type(e).__name__}")
        return {"url": url, "stato": 0, "finale": url, "nodi": None}


def ciclo(page):
    esiti, giro, aperte, bloccate = [], 0, 0, 0
    while giro < MAX_GIRI:
        r = manda("/motore/bolighub", {"esiti": esiti, "round": giro}, timeout=180)
        if r is None:
            log("app non raggiungibile")
            return False
        da = r.get("da_leggere", [])
        log(f"giro {giro}: ricevute {len(esiti)} pagine, richieste {len(da)}, verificati {r.get('verificati', 0)}")
        if not da:
            return True
        esiti = []
        for u in da[:MAX_PER_GIRO]:
            e = leggi(page, u)
            aperte += 1
            bloccate += e["stato"] == 403
            esiti.append(e)
            time.sleep(PAUSA)
        giro += 1
    log(f"ciclo interrotto dopo {MAX_GIRI} giri ({aperte} pagine aperte, {bloccate} bloccate)")
    return True


def main(minuti):
    fine = time.time() + minuti * 60
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=UA_ARGS)
        ctx = browser.new_context(viewport={"width": 1260, "height": 860}, locale="en-GB", timezone_id="Europe/Copenhagen")
        page = ctx.new_page()
        while time.time() < fine:
            t0 = time.time()
            try:
                ciclo(page)
            except Exception as e:
                log(f"ciclo fallito: {type(e).__name__}")
                try:
                    page.close()
                except Exception:
                    pass
                page = ctx.new_page()
            attesa = CICLO_S - (time.time() - t0)
            if attesa > 0 and time.time() + attesa < fine:
                time.sleep(attesa)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 330))
