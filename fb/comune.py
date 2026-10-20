"""Pezzi comuni: browser, lettura dei dati GraphQL, stato della sessione.

Regola per tutto il motore: il repository e' pubblico e i registri di GitHub li
vede chiunque. Nei registri si scrivono solo numeri, mai testi, nomi o link.
"""
import base64, json, random, re, time, datetime
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


# --- Accesso a Facebook dal telefono ---------------------------------------------
# Quando Facebook scollega la sessione, si apre la pagina di accesso nel vero Google Chrome
# (non nel browser automatico: con quello Facebook fa ripetere il captcha all'infinito) e se
# ne manda l'immagine all'app (solo il proprietario la vede, dentro Telegram). Dall'app tocchi
# e scrivi: tocchi e testo tornano qui e vengono eseguiti su QUELLA pagina, e solo questi
# gesti. Tutto passa dal server dell'app: nessun collegamento aperto verso questo computer.
# Fatto l'accesso, i cookie passano al motore. Nei registri pubblici non va nulla di questo.
TASTI = {"Enter", "Backspace", "Tab", "Escape"}
CHROME_VERO = "/usr/bin/google-chrome"


def _esegui(pagina, e, w, h):
    t = e.get("tipo")
    if t == "tap":
        pagina.mouse.click(max(0, min(w, float(e["x"]))), max(0, min(h, float(e["y"]))))
    elif t == "testo":
        pagina.keyboard.type(str(e.get("t", ""))[:300], delay=35)
    elif t == "tasto" and e.get("k") in TASTI:
        pagina.keyboard.press(e["k"])
    elif t == "scorri":
        pagina.mouse.wheel(0, max(-800, min(800, float(e.get("dy", 0)))))
    elif t == "ricarica":
        pagina.goto("https://www.facebook.com/login/", wait_until="domcontentloaded", timeout=60000)


def _dentro(cctx, pagina):
    nomi = {c["name"] for c in cctx.cookies("https://www.facebook.com")}
    return "c_user" in nomi and not re.search(r"checkpoint|two_step|/login", pagina.url)


def accesso_remoto(pw, manda, scadenza, ogni=45 * 60):
    """Aspetta che tu rientri in Facebook dall'app sul telefono.
    Restituisce i cookie di Facebook se l'accesso e' fatto, altrimenti None."""
    import os, shutil, subprocess, tempfile
    cartella = tempfile.mkdtemp(prefix="accesso-")
    chrome = subprocess.Popen([CHROME_VERO, f"--user-data-dir={cartella}", "--remote-debugging-port=9335",
                               "--no-first-run", "--no-default-browser-check", "--window-position=0,0",
                               "--window-size=430,900", "--lang=da-DK", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, DISPLAY=":99"))
    try:
        browser = None
        for _ in range(30):
            try:
                browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9335")
                break
            except Exception:
                time.sleep(1)
        if not browser:
            log("accesso dal telefono: Chrome non parte")
            return None
        cctx = browser.contexts[0]
        pagina = cctx.pages[0] if cctx.pages else cctx.new_page()
        pagina.goto("https://www.facebook.com/login/", wait_until="domcontentloaded", timeout=60000)
        avviso = lambda: manda("/motore/stato", {"accesso": {"attivo": True, "minuti": round((scadenza - time.time()) / 60)}})
        avviso()
        log("accesso dal telefono: in attesa")
        ultimo_avviso = ultimo_evento = time.time()
        while time.time() < scadenza:
            try:
                w, h = pagina.evaluate("[innerWidth, innerHeight]")
                img = base64.b64encode(pagina.screenshot(type="jpeg", quality=60)).decode()
            except Exception:
                w, h, img = 412, 780, None
            r = manda("/motore/schermo", {"img": img, "w": w, "h": h}) or {}
            eventi = r.get("eventi") or []
            for e in eventi:
                try:
                    _esegui(pagina, e, w, h)
                except Exception:
                    pass
            if eventi:
                ultimo_evento = time.time()
                time.sleep(0.4)  # si rimanda subito l'immagine aggiornata
                continue
            if _dentro(cctx, pagina):
                time.sleep(20)  # lascia finire a Facebook i passaggi dopo l'accesso
                if _dentro(cctx, pagina):
                    cookie = [c for c in cctx.cookies() if "facebook.com" in c["domain"]]
                    manda("/motore/stato", {"accesso": {"fatto": True}})
                    log("accesso dal telefono: fatto")
                    return cookie
            # Veloce mentre stai usando lo schermo, lento quando non c'e' nessuno.
            time.sleep(0.3 if time.time() - ultimo_evento < 120 else 4)
            if time.time() - ultimo_avviso > ogni:
                avviso()
                ultimo_avviso = time.time()
        manda("/motore/stato", {"accesso": {"scaduto": True}})
        log("accesso dal telefono: tempo scaduto")
        return None
    except Exception as e:
        log(f"accesso dal telefono: errore {type(e).__name__}")
        return None
    finally:
        chrome.terminate()
        time.sleep(2)
        shutil.rmtree(cartella, ignore_errors=True)


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


def cammina(o, f, salta=None):
    """Visita tutti i dizionari; salta(chiave) permette di non entrare in certi rami."""
    if isinstance(o, dict):
        f(o)
        for k, v in o.items():
            if salta and salta(k):
                continue
            cammina(v, f, salta)
    elif isinstance(o, list):
        for v in o:
            cammina(v, f, salta)


# Facebook mette accanto al post la sua traduzione automatica nella lingua dell'account
# (italiano): va ignorata, il testo da leggere e' l'originale. Anche i post condivisi dentro
# un post (attached_story) hanno un testo loro, che non e' quello dell'annuncio.
def _ramo_da_saltare(k):
    k = str(k).lower()
    return "translat" in k or k in ("attached_story", "attached_story_", "comet_sections_attached")


CHIAVI_IMMAGINE = ("image", "viewer_image", "photo_image", "large_share_image", "image_high", "full_image", "imageHigh")


def immagine_di(foto):
    """Il link dell'immagine di un nodo Photo. Facebook la mette sotto chiavi diverse a seconda del tipo di post
    (16/10/2026: 115 case su 326 senza foto, si leggevano solo "image" e "viewer_image"): si prende la piu' grande."""
    migliori = []
    for k in CHIAVI_IMMAGINE:
        v = foto.get(k)
        if isinstance(v, dict) and isinstance(v.get("uri"), str) and "fbcdn" in v["uri"]:
            migliori.append((v.get("width") or 0, v["uri"]))
    t = foto.get("preferred_thumbnail")
    if isinstance(t, dict) and isinstance(t.get("image"), dict) and isinstance(t["image"].get("uri"), str):
        migliori.append((t["image"].get("width") or 0, t["image"]["uri"]))
    return max(migliori)[1] if migliori else None


def post_da(risposte):
    """Tutti i post (Story) trovati nelle risposte, con testo, data e foto."""
    tutti = {}
    for body in risposte:
        for obj in oggetti(body):
            def visita(d):
                if d.get("__typename") != "Story" or not d.get("post_id"):
                    return
                p = tutti.setdefault(d["post_id"], {"id": d["post_id"], "testo": "", "tempo": None,
                                                    "foto": {}, "foto_totali": 0, "url": None, "autore": None})
                # Il testo del post stesso, se c'e' al primo livello, vale piu' di qualunque altro.
                proprio = d.get("message") if isinstance(d.get("message"), dict) else None
                if proprio and isinstance(proprio.get("text"), str) and proprio["text"]:
                    p["proprio"] = True
                    p["testo"] = proprio["text"]
                def dentro(x):
                    # Chi ha pubblicato (solo il numero del profilo, non il nome): serve a riconoscere
                    # lo stesso annuncio scritto in lingue diverse o ripubblicato con altre parole.
                    # Nei dati del gruppo l'autore sta in feedback.owning_profile (accanto a post_id);
                    # "actors" c'e' solo nel nodo esterno (visto sulla pagina vera il 28/09/2026).
                    a = x.get("actors")
                    o = x.get("owning_profile")
                    if not p["autore"] and isinstance(o, dict) and o.get("id"):
                        p["autore"] = str(o["id"])
                    elif not p["autore"] and isinstance(a, list) and a and isinstance(a[0], dict) and a[0].get("id"):
                        p["autore"] = str(a[0]["id"])
                    if isinstance(x.get("creation_time"), int) and not p["tempo"]:
                        p["tempo"] = x["creation_time"]
                    m = x.get("message")
                    if not p.get("proprio") and isinstance(m, dict) and isinstance(m.get("text"), str) and len(m["text"]) > len(p["testo"]):
                        p["testo"] = m["text"]
                    if x.get("__typename") == "Photo" and x.get("id"):
                        uri = immagine_di(x)
                        if uri:
                            p["foto"][x["id"]] = uri
                        else:
                            p["foto"].setdefault(x["id"], None)
                    s = x.get("all_subattachments")
                    if isinstance(s, dict) and isinstance(s.get("count"), int):
                        p["foto_totali"] = max(p["foto_totali"], s["count"])
                    if isinstance(x.get("url"), str) and "/groups/" in x["url"] and not p["url"]:
                        p["url"] = x["url"]
                cammina(d, lambda x: isinstance(x, dict) and dentro(x), _ramo_da_saltare)
            cammina(obj, visita)
    # Secondo passaggio per l'autore: Facebook manda i post anche a pezzi (non sempre con
    # __typename "Story"); qualunque pezzo con lo stesso post_id e l'autore accanto va bene.
    senza = {pid for pid, p in tutti.items() if not p.get("autore")}
    if senza:
        def cerca(d):
            pid = d.get("post_id")
            if pid not in senza or tutti[pid].get("autore"):
                return
            fb = d.get("feedback") if isinstance(d.get("feedback"), dict) else {}
            o = fb.get("owning_profile") or d.get("owning_profile")
            a = d.get("actors")
            if isinstance(o, dict) and o.get("id"):
                tutti[pid]["autore"] = str(o["id"])
            elif isinstance(a, list) and a and isinstance(a[0], dict) and a[0].get("id"):
                tutti[pid]["autore"] = str(a[0]["id"])
        for body in risposte:
            for obj in oggetti(body):
                cammina(obj, lambda x: isinstance(x, dict) and cerca(x), _ramo_da_saltare)
    for p in tutti.values():
        p.pop("proprio", None)
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


def leggi_gruppo(page, gid, scroll=8):
    # Ritmo da persona: pause un po' diverse ogni volta e meno scorrimento (ogni 30 minuti
    # bastano gli ultimi post). Il 23/09/2026 un ritmo piu' fitto ha fatto bloccare la lettura
    # dei gruppi da Facebook per un giorno e mezzo.
    cima = []  # cosa mostra la pagina appena aperta (i post piu' nuovi), per la misura di copertura

    def scorri(n):
        for _ in range(n):
            page.mouse.move(random.randint(450, 750), random.randint(380, 620))
            page.mouse.wheel(0, random.randint(1900, 2700))
            time.sleep(random.uniform(1.8, 3.4))
        time.sleep(random.uniform(1.5, 3))

    def azione():
        page.goto(f"https://www.facebook.com/groups/{gid}/?sorting_setting=CHRONOLOGICAL",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(random.uniform(5, 8))
        page.keyboard.press("Escape")
        try:
            cima.append(page.evaluate(_JS_CIMA))
        except Exception:
            pass
        scorri(scroll)

    risposte = registra(page, azione)
    # Il nome del gruppo (dal titolo della pagina): va solo all'app, mai nei log pubblici.
    try:
        nome = re.sub(r"^\(\d+\+?\)\s*", "", page.title())
        nome = re.sub(r"\s*\|\s*Facebook\s*$", "", nome).strip()
        if nome and nome.lower() != "facebook":
            NOMI_GRUPPI[gid] = nome
    except Exception:
        pass
    posts = post_da(risposte)
    # Profondita': tra due letture dello stesso gruppo passano 30 minuti. Se il post piu' vecchio letto
    # e' uscito da meno di 50 minuti, in un gruppo molto attivo potrebbero restarne fuori: si scorre
    # ancora (al massimo 6 volte) e si rilegge.
    extra = 0
    try:
        tempi = [p["tempo"] for p in posts.values() if p.get("tempo")]
        if tempi and time.time() - min(tempi) < 50 * 60:
            extra = 6
            risposte += registra(page, lambda: scorri(extra))
            posts = post_da(risposte)
    except Exception:
        pass
    # Misura (solo osservazione, mai nei log pubblici): i post che la pagina mostra e il motore non ha catturato.
    try:
        m = misura_copertura(cima[0] if cima else None, posts)
        m["scroll_extra"] = extra
        # Post mostrati dalla pagina e non catturati: si aprono direttamente (al massimo 3 per gruppo e per giro) e si aggiungono ai
        # post letti. E' il recupero di quello che la lettura del feed perde (20/10/2026: l'utente trova su Facebook case che l'app non ha).
        mancanti = m.pop("id_mancanti", [])
        recuperati = 0
        for pid in mancanti[:3]:
            try:
                def apri_post(pid=pid):
                    page.goto(f"https://www.facebook.com/groups/{gid}/posts/{pid}/", wait_until="domcontentloaded", timeout=60000)
                    time.sleep(random.uniform(5, 7))
                trovati = post_da(registra(page, apri_post))
                p = trovati.get(pid) or next((x for x in trovati.values() if x.get("testo")), None)
                if p and p.get("testo"):
                    p["id"] = pid
                    posts[pid] = p
                    recuperati += 1
            except Exception:
                pass
        m["id_mancanti_n"] = len(mancanti)
        m["id_recuperati"] = recuperati
        COPERTURA[gid] = m
    except Exception:
        pass
    return posts


NOMI_GRUPPI = {}

# Copertura della lettura (02/10/2026, l'utente teme che il motore non catturi tutti i post). Appena aperta
# la pagina del gruppo si guarda cosa mostra in cima (i post piu' nuovi: la pagina tiene in memoria solo
# quelli vicini a dove si e'): il testo dei messaggi dei post e dei blocchi del feed. Quelli che non
# corrispondono a nessun post catturato sono post mostrati e persi. Funziona sul testo, perche' Facebook
# nasconde i link dei post. Il primo tentativo contava "role=article", che su Facebook sono i COMMENTI:
# misurava altro. Finisce solo nel database privato dell'app, nel registro pubblico solo i totali.
COPERTURA = {}
_JS_CIMA = """() => {
  const testi = (sel) => [...document.querySelectorAll(sel)].map(e => (e.innerText || '').slice(0, 320));
  const messaggi = [...testi('[data-ad-preview="message"]'), ...testi('[data-ad-comet-preview="message"]')];
  const feed = document.querySelector('div[role="feed"]');
  const blocchi = feed ? [...feed.children].map(c => (c.innerText || '').slice(0, 500)) : [];
  // ID dei post mostrati (dai link alla data del post): confronto esatto con quelli catturati (20/10/2026).
  const ids = [...new Set([...document.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"]')].map(a => {
    const h = a.href; const k = h.includes('/posts/') ? '/posts/' : '/permalink/';
    const id = (h.split(k)[1] || '').split('/')[0].split('?')[0];
    return /^[0-9]+$/.test(id) ? id : null;
  }).filter(Boolean))];
  return {messaggi, blocchi, ids, feed: !!feed, commenti: document.querySelectorAll('div[role="article"]').length};
}"""


def misura_copertura(cima, posts):
    if not cima:
        return None
    # Solo lettere e cifre: la pagina non mostra le emoji nel testo e taglia i post lunghi con "... altro".
    norm = lambda s: re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", (s or "").lower())).strip()
    firme = [norm(p.get("testo"))[:18] for p in posts.values()]
    firme = [f for f in firme if len(f) >= 12]
    trovato = lambda n: any(f in n for f in firme)
    # Blocchi finti di Facebook ("facebook facebook facebook ..."): non sono post.
    # (Facebook oscura il testo di molti blocchi con la parola "facebook" ripetuta: non e' leggibile, non si misura.)
    veri = lambda n: len(set(n.split()) - {"facebook"}) > 4
    # I messaggi dei post (testo del post, senza intestazione ne' commenti).
    msg = [norm(t) for t in cima.get("messaggi", [])]
    msg = [n for n in dict.fromkeys(msg) if len(n) >= 25 and veri(n)]
    msg_persi = [n for n in msg if not trovato(n)]
    # I blocchi del feed (un blocco = un post con intestazione e reazioni): solo quelli con testo vero.
    blocchi = [norm(t) for t in cima.get("blocchi", [])]
    blocchi = [n for n in blocchi if len(n) >= 120 and veri(n) and "mi piace rispondi" not in n[:200]]
    blocchi_persi = [n for n in blocchi if not trovato(n)]
    # Confronto piu' robusto (19/10/2026): la prova sui primi 18 caratteri sbaglia se Facebook oscura o cambia l'inizio. Un blocco
    # corrisponde a un post catturato se contiene almeno il 60% delle sue prime parole "vere" (4+ lettere).
    parole_post = []
    for p in posts.values():
        w = [x for x in norm(p.get("testo")).split() if len(x) >= 4][:14]
        if len(w) >= 5:
            parole_post.append(set(w))
    def corrisponde(n):
        bw = set(n.split())
        return any(len(w & bw) >= 0.6 * len(w) for w in parole_post)
    persi_forti = [n for n in blocchi_persi if not corrisponde(n)]
    # Misura che non dipende dal testo (Facebook lo scompone nella pagina: "n d o", "r t"): i blocchi del feed con l'ora scritta
    # ("17 minuti fa", "3 ore fa") contro i post catturati con quell'ora (creation_time). Se i visibili sono piu' dei catturati,
    # qualche post mostrato dalla pagina non e' stato catturato.
    def minuti_fa(n):
        m = re.search(r"\b(\d+) minut[io] fa", n)
        if m: return int(m.group(1))
        if re.search(r"\bun minuto fa", n): return 1
        if re.search(r"\b(?:circa )?un ora fa", n): return 60
        m = re.search(r"\b(\d+) ore fa", n)
        return int(m.group(1)) * 60 if m else None
    visibili_ora = [x for x in (minuti_fa(n) for n in [norm(t) for t in cima.get("blocchi", [])] if len(n) >= 40) if x is not None and x <= 180]
    adesso = time.time()
    catturati_ora = [1 for p in posts.values() if p.get("tempo") and adesso - p["tempo"] <= 200 * 60]
    tempi = [p["tempo"] for p in posts.values() if p.get("tempo")]
    ids_dom = [str(x) for x in cima.get("ids", [])]
    return {"id_dom": len(ids_dom), "id_mancanti": [x for x in ids_dom if x not in posts], "visibili_ora": len(visibili_ora), "catturati_ora": len(catturati_ora), "messaggi": len(msg), "messaggi_persi": len(msg_persi), "blocchi": len(blocchi), "blocchi_persi": len(blocchi_persi), "persi_forti": len(persi_forti),
            "feed": bool(cima.get("feed")), "catturati": len(posts),
            "piu_vecchio_min": round((time.time() - min(tempi)) / 60) if tempi else None,
            "esempi": [n[:450] for n in (msg_persi or persi_forti)[:5]]}




_JS_GRUPPI = r"""() => {
  const fuori = new Set(['joins', 'discover', 'feed', 'create', 'search', 'category', 'notifications', 'requests', 'recommendations']);
  const out = {};
  for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
    const m = a.href.match(/facebook\.com\/groups\/([^\/?#]+)/);
    if (!m || fuori.has(m[1])) continue;
    const nome = ((a.getAttribute('aria-label') || a.innerText || '').trim().split('\n')[0] || '').slice(0, 90);
    if (!(m[1] in out) || nome.length > out[m[1]].length) out[m[1]] = nome;
  }
  return out;
}"""


def elenca_gruppi_account(page):
    """I gruppi a cui l'account e' iscritto (19/10/2026: un post di una casa non era nell'app e potrebbe stare in un gruppo non letto).
    Ritorna [{id, nome}]. I nomi vanno solo nel database privato dell'app, mai nel registro pubblico."""
    page.goto("https://www.facebook.com/groups/joins/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(6)
    trovati = {}
    fermi = 0
    # Si scorre finche' compaiono gruppi nuovi (il 20/10/2026 l'elenco si fermava sempre a 32 e un gruppo appena iscritto mancava):
    # al massimo 70 scorrimenti, si smette dopo 6 di fila senza novita'.
    for _ in range(70):
        prima = len(trovati)
        try:
            for k, v in page.evaluate(_JS_GRUPPI).items():
                if k not in trovati or len(v) > len(trovati[k]):
                    trovati[k] = v
        except Exception:
            pass
        fermi = fermi + 1 if len(trovati) == prima else 0
        if fermi >= 6:
            break
        page.mouse.move(640, 500)
        page.mouse.wheel(0, 3500)
        time.sleep(2.2)
    return [{"id": k, "nome": v} for k, v in trovati.items()]
