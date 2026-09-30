"""Findbolig (findbolig.nu): legge le case libere e le manda all'app.

Il server di Findbolig non manda il certificato intermedio (RapidSSL TLS RSA CA G1): i browser
lo recuperano da soli, Cloudflare no (errore 526). Qui si aggiunge quel certificato pubblico
(rapidssl_g1.pem, da cacerts.digicert.com) e la verifica resta completa.

Regole del registro pubblico: solo numeri. Nessun testo, nome o link.
"""
import json, re, ssl, sys, time, html, urllib.request
from pathlib import Path
from comune import log
from motore_invio import manda

BASE = "https://findbolig.nu"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
CTX = ssl.create_default_context()
CTX.load_verify_locations(cafile=str(Path(__file__).parent / "rapidssl_g1.pem"))
ATTIVI = {"Published", "PublishedNotScreened"}


def richiesta(url, corpo=None):
    dati = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dati, method="POST" if dati else "GET",
                                 headers={"User-Agent": UA, "content-type": "application/json", "Accept-Language": "da-DK,da;q=0.9"})
    with urllib.request.urlopen(req, context=CTX, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def cerca(filtri, quanti=100, pagina=0):
    return json.loads(richiesta(f"{BASE}/api/search", {"pageSize": quanti, "page": pagina, "orderBy": "Created",
                                                        "orderDirection": "DESC", "mixedResults": False, "filters": filtri}))


def attiva(r):
    return r.get("residenceAdvertStatus") in ATTIVI and r.get("typeIndividualResidence") is True


def descrizione(pagina_html):
    m = re.search(r'<c-show-more\s+description="([^"]*)"', pagina_html)
    if not m:
        return None
    h = html.unescape(m.group(1))
    h = re.sub(r"</p>\s*<p>|<br\s*/?>", "\n", h)
    return html.unescape(re.sub(r"<[^>]+>", " ", h)).strip() or None


def main():
    # 1. Cosa c'e' gia' nell'app: gli annunci ancora attivi e quelli che hanno gia' la descrizione.
    app = manda("/motore/findbolig", {"fase": "attivi"})
    if app is None:
        log("app non raggiungibile")
        return 1
    attivi, con_testo = set(app.get("attivi", [])), set(app.get("con_testo", []))

    # 2. Tutte le case libere di Copenaghen e Frederiksberg (una quarantina: una pagina basta).
    risultati, pagina = [], 0
    while True:
        j = cerca({"Commune": ["København", "Frederiksberg"], "Type": "Residence", "TypeIndividualResidence": "true"}, 100, pagina)
        risultati += j["results"]
        if len(j["results"]) < 100 or pagina >= 10:
            break
        pagina += 1
    liberi = [r for r in risultati if attiva(r)]
    ids = {str(r["shortId"]) for r in liberi}

    # 3. Descrizione (solo nella pagina della casa) per quelle che non l'hanno ancora.
    descrizioni, falliti = {}, 0
    for r in liberi:
        sid = str(r["shortId"])
        if sid in con_testo:
            continue
        try:
            descrizioni[sid] = descrizione(richiesta(f"{BASE}/residence/{sid}"))
        except Exception:
            falliti += 1
        time.sleep(1.5)

    # 4. Gli annunci dell'app che non sono piu' nella lista: si chiede il loro stato al sito.
    #    Solo una risposta esplicita (affittata, riservata o non trovata) li toglie.
    stati = {}
    mancanti = sorted(attivi - ids)
    for i in range(0, len(mancanti), 50):
        pezzo = mancanti[i:i + 50]
        j = cerca({"ShortId": [int(x) for x in pezzo]}, len(pezzo))
        trovati = {str(r["shortId"]): r for r in j["results"]}
        for sid in pezzo:
            stati[sid] = "attivo" if sid in trovati and attiva(trovati[sid]) else "sparito"

    esito = manda("/motore/findbolig", {"risultati": liberi, "descrizioni": descrizioni, "stati": stati, "totale": len(risultati)})
    log(f"findbolig: liberi={len(liberi)} descrizioni={len(descrizioni)} falliti={falliti} "
        f"controllati={len(stati)} esito={json.dumps(esito)[:200] if isinstance(esito, dict) else 'nessuno'}")
    return 0 if esito is not None else 1


PAUSA = 20 * 60


def ciclo(minuti):
    """Una lettura ogni 20 minuti per `minuti` minuti. Un errore salta un giro, non ferma il ciclo:
    il workflow deve finire bene per ripartire da solo (gli orari automatici di GitHub non bastano:
    il 29-30/09/2026 ha lanciato 3 esecuzioni in 16 ore invece di 48)."""
    fine = time.time() + minuti * 60
    while True:
        t0 = time.time()
        try:
            main()
        except Exception as e:
            log(f"findbolig: errore {type(e).__name__}")
        if time.time() + PAUSA > fine:
            return 0
        time.sleep(max(60, t0 + PAUSA - time.time()))


if __name__ == "__main__":
    sys.exit(ciclo(int(sys.argv[1])) if len(sys.argv) > 1 else main())
