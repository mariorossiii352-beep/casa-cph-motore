"""Invio al server dell'app con il token firmato da GitHub (usato da motore.py, findbolig.py e accesso_telefono.py)."""
import json, os, time, urllib.request
from comune import log

APP = "https://casa-cph-nuova.mariorossiii352.workers.dev"
_TOKEN = {"v": None, "t": 0}


def token_github():
    # Il token firmato da GitHub vale qualche minuto: si riusa per 4 (lo schermo per l'accesso
    # dal telefono manda piu' richieste al secondo).
    if _TOKEN["v"] and time.time() - _TOKEN["t"] < 240:
        return _TOKEN["v"]
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=casa-cph"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        _TOKEN.update(v=json.load(r)["value"], t=time.time())
    return _TOKEN["v"]


def manda(percorso, dati, timeout=60, pausa=3):
    corpo = json.dumps(dati).encode()
    for tentativo in range(3):
        try:
            req = urllib.request.Request(APP + percorso, data=corpo, method="POST",
                                         headers={"Authorization": "Bearer " + token_github(), "content-type": "application/json",
                                                  "User-Agent": "casa-cph-motore/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            log(f"invio {percorso} tentativo {tentativo + 1}: {type(e).__name__}")
            time.sleep(pausa)
    return None
